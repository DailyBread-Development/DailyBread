import os
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[1]

backend_env_path = BASE_DIR / ".env"
root_env_path = ROOT_DIR / ".env"

for env_path in (backend_env_path, root_env_path):
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _get_env(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return None

# Environment variables
DISCORD_CLIENT_ID = _get_env("DISCORD_CLIENT_ID", "discord_client_id")
DISCORD_CLIENT_SECRET = _get_env("DISCORD_CLIENT_SECRET", "discord_client_secret")
DISCORD_REDIRECT_URI = _get_env("DISCORD_REDIRECT_URI", "discord_redirect_uri")
PUBLIC_BASE_URL = _get_env("PUBLIC_BASE_URL", "CLOUDFLARE_TUNNEL_URL", "cloudflare_tunnel_url")
SESSION_SECRET = _get_env("SESSION_SECRET", "session_secret")

# Error .env not found
if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET or not SESSION_SECRET:
    raise RuntimeError(
        "Missing one or more required environment variables: DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, "
        "SESSION_SECRET. Set DISCORD_REDIRECT_URI or PUBLIC_BASE_URL for Cloudflare Tunnel/local OAuth."
    )

# Discord API endpoints and session config
DISCORD_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"
DISCORD_GUILDS_URL = "https://discord.com/api/users/@me/guilds"
SESSION_COOKIE_NAME = "dailybread_session"
STATE_COOKIE_NAME = "dailybread_oauth_state"
SESSION_MAX_AGE = 60 * 60 * 24 * 7
STATE_MAX_AGE = 600

serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="dailybread-session")


# Building Avater Url
def build_avatar_url(user: dict[str, str]) -> str:
    if user.get("avatar"):
        return f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png?size=256"

    discriminator = user.get("discriminator", "0")
    fallback = int(discriminator) % 5 if discriminator.isdigit() else 0
    return f"https://cdn.discordapp.com/embed/avatars/{fallback}.png"


# Building Guild Icon Url
def build_guild_icon_url(guild: dict[str, str]) -> str | None:
    if guild.get("icon"):
        return f"https://cdn.discordapp.com/icons/{guild['id']}/{guild['icon']}.png?size=96"
    return None


def is_request_secure(request: Request) -> bool:
    """Honor proxy headers so Secure cookies work behind Cloudflare Tunnel/HTTPS frontends."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        proto = forwarded_proto.split(",", 1)[0].strip().lower()
        if proto in {"http", "https"}:
            return proto == "https"

    forwarded_ssl = request.headers.get("x-forwarded-ssl")
    if forwarded_ssl:
        return forwarded_ssl.lower() == "on"

    forwarded = request.headers.get("forwarded")
    if forwarded:
        for part in forwarded.split(";"):
            if "proto=" in part:
                proto = part.split("=", 1)[1].strip('"').lower()
                if proto in {"http", "https"}:
                    return proto == "https"

    return request.url.scheme == "https"


# A Session Cookie contains the Discord user info and their guilds, and is used to authenticate requests to the backend.
def create_session_cookie_value(user: dict, guilds: list[dict]) -> str:
    payload = {
        "user": user,
        "guilds": guilds,
        "created_at": int(time.time()),
    }
    return serializer.dumps(payload)


# Parses the session cookie and returns the payload if valid, or None if invalid or expired.
def parse_session_cookie(cookie_value: str) -> dict | None:
    try:
        return serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


# A State Cookie is used to store the OAuth state parameter during the Discord login flow, to prevent CSRF attacks.
def get_session(request: Request) -> dict | None:
    raw_session = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_session:
        return None
    return parse_session_cookie(raw_session)


def get_oauth_redirect_uri(request: Request | None = None) -> str:
    """Resolve the Discord OAuth callback URL for local hosting or Cloudflare Tunnel."""

    if DISCORD_REDIRECT_URI:
        return DISCORD_REDIRECT_URI.rstrip("/")

    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL.rstrip('/')}/callback"

    if request is not None:
        return str(request.url_for("oauth_callback_with_slash")).rstrip("/")

    raise RuntimeError("DISCORD_REDIRECT_URI or PUBLIC_BASE_URL is required for OAuth.")


# Creates the Discord authorization URL for the given state string.
def get_login_redirect_url(state: str, request: Request | None = None) -> str:
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": get_oauth_redirect_uri(request),
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
        "prompt": "consent",
        "integration_type": "0",
    }
    return f"{DISCORD_AUTHORIZE_URL}?{urlencode(params)}"


# Exchanges the authorization code for an access token, and returns the token data.
def exchange_code_for_token(code: str, redirect_uri: str | None = None) -> dict:
    response = requests.post(
        DISCORD_TOKEN_URL,
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or get_oauth_redirect_uri(),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    response_data = response.json()
    if response.status_code != 200 or "access_token" not in response_data:
        raise HTTPException(
            status_code=400,
            detail="Unable to complete Discord authorization. Please try again.",
        )
    return response_data


# Fetches the user's Discord profile using the access token, and returns the user data.
def fetch_discord_user(access_token: str) -> dict:
    response = requests.get(
        DISCORD_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


# Fetches the user's Discord guilds using the access token, and returns a list of guild data.
def fetch_discord_guilds(access_token: str) -> list[dict]:
    response = requests.get(
        DISCORD_GUILDS_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
