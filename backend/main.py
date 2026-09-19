import asyncio
import logging  # noqa: I001
import os
import secrets
import traceback
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as fastapi_http_exception_handler
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.auth import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    SESSION_MAX_AGE,
    STATE_MAX_AGE,
    build_avatar_url,
    build_guild_icon_url,
    create_session_cookie_value,
    get_login_redirect_url,
    get_oauth_redirect_uri,
    get_session,
    is_request_secure,
    exchange_code_for_token,
    fetch_discord_guilds,
    fetch_discord_user,
)
from backend.config import (
    DEVELOPMENT_GUILD_ID,
    DOCS_DIR,
    STAFF_DOCUMENTS,
    STAFF_DOCUMENT_ROLES,
    STATIC_DIR,
    TEMPLATES_DIR,
)
from backend.routes import router as routes_router
from backend.services import discord_service, database_service, youversion_service
from backend.services.media_service import get_media_storage_dir

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", os.getenv("discord_client_id", ""))


app = FastAPI(title="DailyBread", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
media_dir = get_media_storage_dir()
app.mount("/media", StaticFiles(directory=str(media_dir), html=False), name="media")
app.include_router(routes_router)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _load_docs_file(filename: str) -> str:
    file_path = DOCS_DIR / filename
    if not file_path.exists():
        return "<p class=\"docs-placeholder\">This document could not be found.</p>"
    return file_path.read_text(encoding="utf-8")


def _load_staff_document_asset(slug: str, page_number: int = 1) -> str | None:
    document = next((doc for doc in STAFF_DOCUMENTS if doc["slug"] == slug), None)
    if document is None:
        return None

    if page_number < 1:
        page_number = 1
    asset_base = str(document.get("asset_base") or document.get("title") or slug)
    page_filename = f"{asset_base}.svg" if page_number == 1 else f"{asset_base} ({page_number}).svg"
    asset_path = DOCS_DIR / str(document.get("directory") or "staff_guides") / page_filename
    if asset_path.exists():
        return str(asset_path)

    legacy_candidates = [
        DOCS_DIR / "staff_guides" / document.get("asset_name", ""),
        DOCS_DIR / str(document.get("directory") or "staff_guides") / slug,
        DOCS_DIR / str(document.get("directory") or "staff_guides") / f"{slug}.svg",
        DOCS_DIR / str(document.get("directory") or "staff_guides") / f"{document['title']}.svg",
    ]
    for candidate in legacy_candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _get_staff_document_by_slug(slug: str) -> dict | None:
    return next((doc for doc in STAFF_DOCUMENTS if doc["slug"] == slug), None)


def _ensure_development_guild_sync_for_user(user_record: dict[str, Any], access_token: str) -> None:
    try:
        guilds_data = fetch_discord_guilds(access_token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Discord guild sync failed while checking staff access user_id=%s error=%s", user_record["id"], exc)
        raise

    guild_match = next((guild for guild in guilds_data if str(guild.get("id", "")) == DEVELOPMENT_GUILD_ID), None)
    if guild_match is None:
        return

    guild_id = str(guild_match.get("id", ""))
    is_owner = guild_match.get("owner") is True
    permissions = int(guild_match.get("permissions", 0) or 0)
    is_admin = is_owner or ((permissions & 0x8) == 0x8)

    db_guild = database_service.upsert_guild(
        guild_id,
        guild_match.get("name", "Development"),
        guild_match.get("icon"),
        str(user_record["discord_id"]) if is_owner else None,
        discord_service.is_bot_in_guild(guild_id),
    )
    guild_member = database_service.upsert_guild_member(db_guild["id"], user_record["id"], is_owner, is_admin)

    _sync_user_roles(guild_id, guild_member, str(user_record["discord_id"]))


def _sync_user_roles(guild_id: str, guild_member: dict[str, Any], discord_user_id: str) -> None:
    guild_roles = discord_service.list_guild_roles(guild_id)
    role_rows = [
        {
            "discord_role_id": str(role.get("id") or ""),
            "name": str(role.get("name") or "Role"),
            "color": int(role.get("color", 0) or 0),
            "position": int(role.get("position", 0) or 0),
            "permissions": int(role.get("permissions", 0) or 0),
        }
        for role in guild_roles
        if role.get("id")
    ]
    if role_rows:
        database_service.upsert_roles(guild_id, role_rows)

    member_roles_payload = discord_service.get_guild_member(guild_id, discord_user_id)
    member_role_ids = []
    for role_id in member_roles_payload.get("roles", []):
        role_row = database_service.get_role_by_discord_id(guild_id, str(role_id))
        if role_row and role_row.get("id"):
            member_role_ids.append(str(role_row["id"]))
    database_service.replace_member_roles(guild_member["id"], member_role_ids)


def _get_authorized_staff_documents_for_session(session: dict[str, Any]) -> list[dict]:
    if not session or not session.get("user"):
        return []

    try:
        user_record = database_service.get_user_by_discord_id(str(session["user"]["id"]))
        if not user_record:
            return []

        oauth_session = database_service.get_latest_oauth_session(user_record["id"])
        if not oauth_session or not oauth_session.get("access_token"):
            return []

        _ensure_development_guild_sync_for_user(user_record, oauth_session["access_token"])

        guild = database_service.get_guild_by_discord_id(DEVELOPMENT_GUILD_ID)
        if guild is None:
            return []

        member_row = database_service.get_guild_member_for_user(guild["id"], user_record["id"])
        if member_row is None:
            return []

        authorized_role_ids = {
            str(role["discord_role_id"]) if role.get("discord_role_id") is not None else str(role["id"])
            for role in database_service.get_member_role_mapping_for_user(user_record["id"], DEVELOPMENT_GUILD_ID)
        }

        authorized_docs = []
        for document in STAFF_DOCUMENTS:
            if document["role_id"] in authorized_role_ids:
                authorized_docs.append(document)
        return authorized_docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("Staff docs authorization failed for Discord user=%s error=%s", session.get("user", {}).get("id"), exc)
        return []


def is_user_authorized_for_staff_guide(session: dict[str, Any], slug: str) -> bool:
    return any(document["slug"] == slug for document in _get_authorized_staff_documents_for_session(session))


def get_staff_documents_for_session(session: dict[str, Any]) -> list[dict]:
    return _get_authorized_staff_documents_for_session(session)


def _is_api_request(request: Request) -> bool:
    if request.url.path.startswith("/api"):
        return True
    accept_header = request.headers.get("accept", "")
    return "application/json" in accept_header


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if _is_api_request(request):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(status_code=exc.status_code, content={"success": False, "error": detail})
    return await fastapi_http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    if _is_api_request(request):
        return JSONResponse(status_code=422, content={"success": False, "error": "Invalid request payload."})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if _is_api_request(request):
        logger.exception("Unhandled API exception", exc_info=exc)
        return JSONResponse(status_code=500, content={"success": False, "error": "Internal server error."})
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# pylint: disable=too-many-arguments
def build_template_context(request: Request, extra: dict | None = None) -> dict:
    session = get_session(request)
    context = {
        "request": request,
        "user": session["user"] if session else None,
        "discord_client_id": DISCORD_CLIENT_ID,
    }
    if extra:
        context.update(extra)
    return context


# pylint: disable=invalid-name 
def _get_user_guilds_from_db(session: dict) -> list[dict]:
    try:
        user_record = database_service.get_user_by_discord_id(str(session["user"]["id"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to load guilds from PostgreSQL; using session guilds. error=%s", exc)
        return session.get("guilds", [])

    if not user_record:
        return session.get("guilds", [])

    guilds = database_service.get_user_guilds(user_record["id"])
    for guild in guilds:
        guild["icon_url"] = build_guild_icon_url({"id": guild.get("guild_id"), "icon": guild.get("icon")})
    return guilds


# pylint: disable=invalid-name
@app.get("/", response_class=HTMLResponse)
async def landing_page(
    request: Request, 
    code: str | None = None,
    state: str | None = None,
) -> Any:
    
    if code and state:
        logger.info("OAuth parameters arrived on landing page; forwarding to callback handler")
        return await oauth_callback(request, code, state)

    daily_verse = youversion_service.get_today()

    return templates.TemplateResponse(
        request,
        "pages/index.html",
        build_template_context(request, {
            "page_title": "DailyBread",
            "active_page": "home",
            "daily_verse": daily_verse,
        }),
    )
# pylint: disable=invalid-name
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if session:
        return RedirectResponse(url="/dashboard")

    return templates.TemplateResponse(
        request,
        "pages/login.html",
        build_template_context(request, {"page_title": "Log in - DailyBread", "active_page": "login"}),
    )


@app.get("/staff/verify")
async def verify_staff_access(request: Request) -> RedirectResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    user = session.get("user")
    if not user:
        return RedirectResponse(url="/login")

    user_record = database_service.get_user_by_discord_id(str(user["id"]))
    if not user_record:
        return RedirectResponse(url="/login")

    oauth_session = database_service.get_latest_oauth_session(user_record["id"])
    if not oauth_session or not oauth_session.get("access_token"):
        return RedirectResponse(url="/login/discord")

    try:
        _ensure_development_guild_sync_for_user(user_record, oauth_session["access_token"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Staff access verification failed for user_id=%s error=%s", user_record["id"], exc)
        return RedirectResponse(url="/login/discord")

    return RedirectResponse(url="/docs")


# pylint: disable=invalid-name
@app.get("/login/discord")
def login_discord(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    redirect_url = get_login_redirect_url(state, request)
    response = RedirectResponse(url=redirect_url, status_code=307)
    secure_cookie = is_request_secure(request)
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    logger.info(
        "OAuth state cookie attached path=/ secure=%s httponly=true samesite=lax host=%s",
        secure_cookie,
        request.headers.get("host"),
    )
    return response


# pylint: disable=invalid-name
@app.get("/callback/")
async def oauth_callback_no_slash(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    return await oauth_callback(request, code, state)


@app.get("/callback")
async def oauth_callback_with_slash(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    return await oauth_callback(request, code, state)


async def oauth_callback(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth callback parameters.")

    expected_state = request.cookies.get(STATE_COOKIE_NAME)
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=403, detail="Invalid OAuth state. Please try again.")

    logger.info("OAuth callback entered")
    try:
        token_data = await asyncio.to_thread(exchange_code_for_token, code, get_oauth_redirect_uri(request))
        logger.info("Discord token exchange succeeded")
        access_token = token_data["access_token"]

        user_data = await asyncio.to_thread(fetch_discord_user, access_token)
        logger.info("Discord user fetched id=%s username=%s", user_data.get("id"), user_data.get("username"))

        guilds_data = await asyncio.to_thread(fetch_discord_guilds, access_token)
        logger.info("Discord guilds fetched count=%s", len(guilds_data))

        logger.info("PostgreSQL OAuth sync started")
        user = {
            "id": user_data["id"],
            "username": user_data["username"],
            "avatar": user_data.get("avatar"),
            "avatar_url": build_avatar_url(user_data),
        }

        user_record = await asyncio.to_thread(
            database_service.upsert_user_by_discord_id,
            discord_id=str(user_data["id"]),
            username=user_data.get("username", ""),
            avatar=user.get("avatar"),
            global_name=user_data.get("global_name", ""),
        )
        # A website login is the only event that updates PostgreSQL. The bot
        # never performs background database synchronization.
        await asyncio.to_thread(database_service.store_oauth_session, user_record["id"], token_data)
        synced_guilds = []
        for guild in guilds_data:
            guild_id = str(guild.get("id", ""))
            is_owner = guild.get("owner") is True
            permissions = int(guild.get("permissions", 0) or 0)
            is_admin = is_owner or ((permissions & 0x8) == 0x8)

            has_bot = False
            try:
                has_bot = await asyncio.to_thread(discord_service.is_bot_in_guild, guild_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bot presence check failed guild_id=%s error=%s", guild_id, exc)

            db_guild = await asyncio.to_thread(
                database_service.upsert_guild,
                guild_id,
                guild.get("name", ""),
                guild.get("icon"),
                str(user_data["id"]) if is_owner else None,
                has_bot,
            )
            await asyncio.to_thread(
                database_service.upsert_guild_member,
                db_guild["id"],
                user_record["id"],
                is_owner,
                is_admin,
            )
            if has_bot:
                try:
                    member_record = await asyncio.to_thread(
                        database_service.get_guild_member_for_user,
                        db_guild["id"],
                        user_record["id"],
                    )
                    await asyncio.to_thread(_sync_user_roles, guild_id, member_record, str(user_data["id"]))
                    channels = await asyncio.to_thread(discord_service.list_guild_channels, guild_id)
                    await asyncio.to_thread(
                        database_service.upsert_channels,
                        guild_id,
                        [
                            {"discord_id": str(channel["id"]), "name": channel.get("name"), "channel_type": channel.get("type", 0), "position": channel.get("position", 0), "category_id": channel.get("parent_id"), "nsfw": channel.get("nsfw", False)}
                            for channel in channels
                        ],
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Guild channel sync failed guild_id=%s error=%s", guild_id, exc)
            synced_guilds.append(
                {
                    "guild_id": guild_id,
                    "name": db_guild["name"],
                    "icon": db_guild.get("icon"),
                    "icon_url": build_guild_icon_url(guild),
                    "has_bot": has_bot,
                    "is_owner": is_owner,
                    "is_admin": is_admin,
                }
            )

        logger.info("PostgreSQL OAuth sync completed guild_count=%s", len(synced_guilds))
    except Exception as exc:
        logger.error("OAuth callback failed: %s\n%s", exc, traceback.format_exc())
        raise

    secure_cookie = is_request_secure(request)
    cookie_domain = None
    logger.info(
        "OAuth session cookie attached path=/ secure=%s httponly=true samesite=lax domain=%s host=%s",
        secure_cookie,
        cookie_domain,
        request.headers.get("host"),
    )
    logger.info("OAuth session creation started user_id=%s", user.get("id"))
    session_value = create_session_cookie_value(user, synced_guilds)
    response = RedirectResponse(url="/dashboard")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_value,
        max_age=SESSION_MAX_AGE,
        path="/",
        domain=cookie_domain,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
    )
    logger.info("OAuth session cookie attached user_id=%s secure=%s path=/", user.get("id"), secure_cookie)
    logger.info("Redirecting authenticated user to /dashboard user_id=%s", user.get("id"))
    response.delete_cookie(STATE_COOKIE_NAME, path="/")
    return response


# Documentation
@app.get("/docs", response_class=HTMLResponse)
async def docs_home_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    staff_docs = get_staff_documents_for_session(session)
    return templates.TemplateResponse(
        request,
        "pages/docs.html",
        build_template_context(request, {
            "page_title": "Documentation - DailyBread",
            "active_page": "docs",
            "user": session["user"],
            "staff_documents": staff_docs,
        }),
    )


@app.get("/docs/staff/{slug}", response_class=HTMLResponse)
async def docs_staff_guide_page(request: Request, slug: str) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    document = _get_staff_document_by_slug(slug)
    if document is None:
        raise HTTPException(status_code=404, detail="Staff guide not found.")

    if not is_user_authorized_for_staff_guide(session, slug):
        raise HTTPException(status_code=403, detail="You are not authorized to view this staff guide.")

    try:
        page_number = int(request.query_params.get("page", "1") or "1")
    except ValueError:
        page_number = 1
    if page_number < 1:
        page_number = 1
    max_pages = int(document.get("page_count") or 3)
    if page_number > max_pages:
        page_number = max_pages

    asset_path = _load_staff_document_asset(slug, page_number)
    if asset_path is None:
        document_body = "<p class=\"docs-placeholder\">This staff guide has not been added yet.</p>"
        asset_url = None
    else:
        asset_url = f"/docs/staff-assets/{slug}/{page_number}"
        document_body = f'<img src="{asset_url}" alt="{document["title"]} page {page_number}" class="docs-svg-document" draggable="false" />'

    return templates.TemplateResponse(
        request,
        "pages/docs-detail.html",
        build_template_context(request, {
            "page_title": f"{document['title']} - DailyBread",
            "active_page": "docs",
            "user": session["user"],
            "document_title": document["title"],
            "last_updated": None,
            "document_body": document_body,
            "guide_pages": list(range(1, max_pages + 1)),
            "current_page": page_number,
            "active_slug": slug,
        }),
    )


@app.get("/docs/staff-assets/{slug}/{page}")
async def docs_staff_asset(request: Request, slug: str, page: str) -> Any:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    if not is_user_authorized_for_staff_guide(session, slug):
        raise HTTPException(status_code=403, detail="You are not authorized to access this staff guide asset.")

    try:
        page_number = int(page)
    except ValueError:
        raise HTTPException(status_code=404, detail="Staff guide page not found.") from None
    if page_number < 1:
        raise HTTPException(status_code=404, detail="Staff guide page not found.")

    asset_path = _load_staff_document_asset(slug, page_number)
    if asset_path is None:
        raise HTTPException(status_code=404, detail="Staff guide asset not found.")

    return FileResponse(asset_path, media_type="image/svg+xml")


@app.get("/docs/help", response_class=HTMLResponse)
async def docs_help_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(
        request,
        "pages/docs-detail.html",
        build_template_context(request, {
            "page_title": "Help - DailyBread",
            "active_page": "docs",
            "user": session["user"],
            "document_title": "Help",
            "last_updated": None,
            "document_body": _load_docs_file("help.html"),
        }),
    )


@app.get("/docs/terms", response_class=HTMLResponse)
async def docs_terms_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(
        request,
        "pages/docs-detail.html",
        build_template_context(request, {
            "page_title": "Terms of Service - DailyBread",
            "active_page": "docs",
            "user": session["user"],
            "document_title": "Terms of Service",
            "last_updated": "June 2026",
            "document_body": _load_docs_file("terms.html"),
        }),
    )


@app.get("/docs/privacy", response_class=HTMLResponse)
async def docs_privacy_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(
        request,
        "pages/docs-detail.html",
        build_template_context(request, {
            "page_title": "Privacy Policy - DailyBread",
            "active_page": "docs",
            "user": session["user"],
            "document_title": "Privacy Policy",
            "last_updated": "June 2026",
            "document_body": _load_docs_file("privacy.html"),
        }),
    )


# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    cookie_present = bool(request.cookies.get(SESSION_COOKIE_NAME))
    logger.info("Dashboard session check cookie_present=%s", cookie_present)
    session = get_session(request)
    if not session:
        if cookie_present:
            logger.info("Dashboard session validation failed: malformed or invalid session")
        else:
            logger.info("Dashboard session validation failed: missing cookie")
        return RedirectResponse(url="/login")

    logger.info("Dashboard session validation succeeded user_id=%s", session.get("user", {}).get("id"))
    guilds = _get_user_guilds_from_db(session)
    return templates.TemplateResponse(
        request,
        "pages/dashboard.html",
        build_template_context(request, {
            "page_title": "Dashboard - DailyBread",
            "active_page": "dashboard",
            "user": session["user"],
            "guilds": guilds,
        }),
    )


# Guild management 
@app.get("/dashboard/guild/{guild_id}", response_class=HTMLResponse)
async def guild_management_page(request: Request, guild_id: str) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    guilds = _get_user_guilds_from_db(session)
    guild = next((g for g in guilds if str(g.get("guild_id")) == str(guild_id)), None)
    if not guild:
        return RedirectResponse(url="/dashboard")

    return templates.TemplateResponse(
        request,
        "pages/guild.html",
        build_template_context(request, {
            "page_title": f"Manage {guild['name']} - DailyBread",
            "active_page": "guild",
            "user": session["user"],
            "guild": guild,
        }),
    )


@app.get("/dashboard/guild/{guild_id}/permissions", response_class=HTMLResponse)
async def guild_permissions_page(request: Request, guild_id: str) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    guilds = _get_user_guilds_from_db(session)
    guild = next((g for g in guilds if str(g.get("guild_id")) == str(guild_id)), None)
    if not guild:
        return RedirectResponse(url="/dashboard")

    user_record = database_service.get_user_by_discord_id(str(session["user"]["id"]))
    membership = database_service.get_guild_membership(user_record["id"], guild_id) if user_record else None
    if not membership or not (membership.get("is_owner") or membership.get("is_admin")):
        return RedirectResponse(url="/dashboard")

    return templates.TemplateResponse(
        request,
        "pages/guild-permissions.html",
        build_template_context(request, {
            "page_title": f"Permissions - {guild['name']} - DailyBread",
            "active_page": "guild",
            "user": session["user"],
            "guild": guild,
        }),
    )


# Guild builder 
@app.get("/dashboard/guild/{guild_id}/builder", response_class=HTMLResponse)
async def guild_builder_page(request: Request, guild_id: str, channel_id: str | None = None) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    guilds = _get_user_guilds_from_db(session)
    guild = next((g for g in guilds if str(g.get("guild_id")) == str(guild_id)), None)
    if not guild:
        return RedirectResponse(url="/dashboard")

    return templates.TemplateResponse(
        request,
        "pages/guild-builder.html",
        build_template_context(request, {
            "page_title": f"Embed Builder - {guild['name']} - DailyBread",
            "active_page": "builder",
            "user": session["user"],
            "guild": guild,
            "selected_channel_id": channel_id or "",
        }),
    )


# Global Editor
@app.get("/dashboard/builder", response_class=HTMLResponse)
async def builder_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    guilds = _get_user_guilds_from_db(session)
    builder_guilds = [guild for guild in guilds if guild.get("has_bot")]
    return templates.TemplateResponse(
        request,
        "pages/builder.html",
        build_template_context(request, {
            "page_title": "Embed Builder - DailyBread",
            "active_page": "builder",
            "user": session["user"],
            "guilds": builder_guilds,
        }),
    )


@app.get("/dashboard/builder/mass-selection", response_class=HTMLResponse)
async def mass_selection_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(
        request,
        "pages/mass-selection.html",
        build_template_context(request, {
            "page_title": "Choose Destinations - DailyBread",
            "active_page": "builder",
            "user": session["user"],
        }),
    )


@app.get("/dashboard/advanced-builder")
async def advanced_builder_page(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/dashboard/builder")


# Logout
@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    response = RedirectResponse(url="/")
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(STATE_COOKIE_NAME, path="/")
    return response


# Health check endpoint to verify that the server is running and responsive. Returns a simple JSON object indicating status.
@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
