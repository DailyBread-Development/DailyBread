import logging  # noqa: I001
import os
from pathlib import Path

from dotenv import load_dotenv


ENVIRONMENT_LOCAL = "local"
ENVIRONMENT_CLOUDFLARE = "cloudflare"
ENVIRONMENT_VARIABLE = "DAILYBREAD_ENV"


def get_runtime_environment() -> str:
    """Return the configured runtime mode."""

    configured_environment = os.getenv(ENVIRONMENT_VARIABLE, "").strip().lower()
    if configured_environment in {ENVIRONMENT_LOCAL, ENVIRONMENT_CLOUDFLARE}:
        return configured_environment

    return ENVIRONMENT_LOCAL


def load_environment_variables() -> None:
    """Load local environment variables when a .env file is available."""

    project_root = Path(__file__).resolve().parents[2]
    backend_env = project_root / "backend" / ".env"
    root_env = project_root / ".env"

    if backend_env.exists():
        load_dotenv(backend_env, override=False)
    elif root_env.exists():
        load_dotenv(root_env, override=False)
    else:
        load_dotenv(override=False)


def configure_logging() -> None:
    """Configure clean console logs for local hosting and Cloudflare Tunnel."""

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def get_discord_token() -> str:
    """Read the Discord bot token from environment variables."""

    token = os.getenv("DISCORD_TOKEN") or os.getenv("discord_token")
    if token:
        return token.strip().strip('"').strip("'")

    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your local or Cloudflare Tunnel environment.")
