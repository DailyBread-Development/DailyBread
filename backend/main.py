import logging  # noqa: I001
import os
import secrets
import traceback
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as fastapi_http_exception_handler
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
    exchange_code_for_token,
    fetch_discord_guilds,
    fetch_discord_user,
)
from backend.config import DOCS_DIR, STATIC_DIR, TEMPLATES_DIR
from backend.routes import router as routes_router
from backend.services import discord_service, database_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", os.getenv("discord_client_id", ""))


app = FastAPI(title="DailyBread", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(routes_router)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _load_docs_file(filename: str) -> str:
    file_path = DOCS_DIR / filename
    if not file_path.exists():
        return "<p class=\"docs-placeholder\">This document could not be found.</p>"
    return file_path.read_text(encoding="utf-8")


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
        return oauth_callback(request, code, state)

    return templates.TemplateResponse(
        request, 
        "pages/index.html", 
        build_template_context(request, {"page_title": "DailyBread", "active_page": "home"}),
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


# pylint: disable=invalid-name
@app.get("/login/discord")
def login_discord(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    redirect_url = get_login_redirect_url(state, request)
    response = RedirectResponse(url=redirect_url, status_code=307)
    secure_cookie = request.url.scheme == "https"
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
    )
    return response


# pylint: disable=invalid-name
@app.get("/callback/")
def oauth_callback_no_slash(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    return oauth_callback(request, code, state)
@app.get("/callback")
def oauth_callback_with_slash(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    return oauth_callback(request, code, state)
def oauth_callback(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth callback parameters.")

    expected_state = request.cookies.get(STATE_COOKIE_NAME)
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=403, detail="Invalid OAuth state. Please try again.")

    logger.info("OAuth callback entered")
    try:
        token_data = exchange_code_for_token(code, get_oauth_redirect_uri(request))
        logger.info("Discord token exchange succeeded")
        access_token = token_data["access_token"]

        user_data = fetch_discord_user(access_token)
        logger.info("Discord user fetched id=%s username=%s", user_data.get("id"), user_data.get("username"))

        guilds_data = fetch_discord_guilds(access_token)
        logger.info("Discord guilds fetched count=%s", len(guilds_data))

        logger.info("PostgreSQL OAuth sync started")
        user = {
            "id": user_data["id"],
            "username": user_data["username"],
            "avatar": user_data.get("avatar"),
            "avatar_url": build_avatar_url(user_data),
        }

        user_record = database_service.upsert_user_by_discord_id(
            discord_id=str(user_data["id"]),
            username=user_data.get("username", ""),
            avatar=user.get("avatar"),
            global_name=user_data.get("global_name", ""),
        )
        # A website login is the only event that updates PostgreSQL. The bot
        # never performs background database synchronization.
        database_service.store_oauth_session(user_record["id"], token_data)
        synced_guilds = []
        for guild in guilds_data:
            guild_id = str(guild.get("id", ""))
            is_owner = guild.get("owner") is True
            permissions = int(guild.get("permissions", 0) or 0)
            is_admin = is_owner or ((permissions & 0x8) == 0x8)

            # FILTER: Only sync guilds where user is owner or admin
            if not is_admin:
                continue

            has_bot = False
            try:
                has_bot = discord_service.is_bot_in_guild(guild_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bot presence check failed guild_id=%s error=%s", guild_id, exc)

            # Only the logged-in user's manageable guilds are written.
            db_guild = database_service.upsert_guild(
                guild_id,
                guild.get("name", ""),
                guild.get("icon"),
                str(user_data["id"]) if is_owner else None,
                has_bot,
            )
            database_service.upsert_guild_member(
                db_guild["id"], user_record["id"], is_owner, is_admin
            )
            if has_bot:
                try:
                    channels = discord_service.list_guild_channels(guild_id)
                    database_service.upsert_channels(guild_id, [
                        {"discord_id": str(channel["id"]), "name": channel.get("name"), "channel_type": channel.get("type", 0), "position": channel.get("position", 0), "category_id": channel.get("parent_id"), "nsfw": channel.get("nsfw", False)}
                        for channel in channels
                    ])
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

    session_value = create_session_cookie_value(user, synced_guilds)
    response = RedirectResponse(url="/dashboard")
    secure_cookie = request.url.scheme == "https"
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
    )
    response.delete_cookie(STATE_COOKIE_NAME)
    return response


# Documentation
@app.get("/docs", response_class=HTMLResponse)
async def docs_home_page(request: Request) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(
        request,
        "pages/docs.html",
        build_template_context(request, {
            "page_title": "Documentation - DailyBread",
            "active_page": "docs",
            "user": session["user"],
        }),
    )


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
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")

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


# Guild builder 
@app.get("/dashboard/guild/{guild_id}/builder", response_class=HTMLResponse)
async def guild_builder_page(request: Request, guild_id: str, channel_id: str | None = None) -> HTMLResponse:
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/login")
    if not channel_id:
        return RedirectResponse(url=f"/dashboard/guild/{guild_id}")

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
            "selected_channel_id": channel_id,
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


@app.get("/dashboard/advanced-builder")
async def advanced_builder_page(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/dashboard/builder")


# Logout
@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    response = RedirectResponse(url="/")
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(STATE_COOKIE_NAME)
    return response


# Health check endpoint to verify that the server is running and responsive. Returns a simple JSON object indicating status.
@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
