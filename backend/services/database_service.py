"""PostgreSQL data access for DailyBread.

All database access is kept here so callers remain independent of connection
details.  The pool is opened lazily, allowing application startup without a
database connection until a database-backed feature is used.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        load_dotenv(env_path, override=False)

LOGGER = logging.getLogger(__name__)
_POOL: ConnectionPool | None = None


class DatabaseError(Exception):
    """Raised for safe, application-level database failures."""


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    values = {key: os.getenv(key) for key in ("DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD")}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise DatabaseError("PostgreSQL database configuration is incomplete.")
    return "postgresql://{user}:{password}@{host}:{port}/{name}".format(
        user=values["DATABASE_USER"], password=values["DATABASE_PASSWORD"],
        host=values["DATABASE_HOST"], port=os.getenv("DATABASE_PORT", "5432"), name=values["DATABASE_NAME"],
    )


def _pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(conninfo=_database_url(), kwargs={"row_factory": dict_row}, open=False)
        _POOL.open(wait=False)
    return _POOL


def _fetch_one(sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
    try:
        with _pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    except Exception as exc:
        LOGGER.exception("PostgreSQL query failed")
        raise DatabaseError("Database operation failed.") from exc


def _fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        with _pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    except Exception as exc:
        LOGGER.exception("PostgreSQL query failed")
        raise DatabaseError("Database operation failed.") from exc


def get_user_by_discord_id(discord_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM users WHERE discord_id = %s LIMIT 1", (discord_id,))


def get_user_id_by_discord_id(discord_id: str) -> Optional[str]:
    user = get_user_by_discord_id(discord_id)
    return user["id"] if user else None


def upsert_user_by_discord_id(discord_id: str, username: str = "", avatar: str | None = None, global_name: str | None = None) -> dict[str, Any]:
    row = _fetch_one("""INSERT INTO users (discord_id, username, avatar, global_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (discord_id) DO UPDATE SET username = EXCLUDED.username, avatar = EXCLUDED.avatar, global_name = EXCLUDED.global_name
        RETURNING *""", (discord_id, username or "Discord user", avatar, global_name))
    assert row is not None
    return row


def store_oauth_session(user_id: str, token_data: dict[str, Any]) -> dict[str, Any]:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data.get("expires_in", 3600)))
    row = _fetch_one("""INSERT INTO oauth_sessions (user_id, access_token, refresh_token, expires_at)
        VALUES (%s, %s, %s, %s) RETURNING *""", (user_id, token_data["access_token"], token_data.get("refresh_token"), expires_at))
    assert row is not None
    return row


def get_latest_oauth_session(user_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM oauth_sessions WHERE user_id = %s ORDER BY created_at DESC LIMIT 1", (user_id,))


def get_guild_by_discord_id(discord_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM guilds WHERE discord_id = %s LIMIT 1", (discord_id,))


def upsert_guild(discord_id: str, name: str, icon: str | None = None, owner_discord_id: str | None = None, has_bot: bool = True) -> dict[str, Any]:
    row = _fetch_one("""INSERT INTO guilds (discord_id, name, icon, owner_discord_id, has_bot)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (discord_id) DO UPDATE SET name = EXCLUDED.name, icon = EXCLUDED.icon,
          owner_discord_id = EXCLUDED.owner_discord_id, has_bot = EXCLUDED.has_bot RETURNING *""",
        (discord_id, name or "Unnamed guild", icon, owner_discord_id, has_bot))
    assert row is not None
    return row


def upsert_guild_member(guild_uuid: str, user_uuid: str, is_owner: bool, is_admin: bool) -> dict[str, Any]:
    row = _fetch_one("""INSERT INTO guild_members (guild_id, user_id, is_owner, is_admin) VALUES (%s, %s, %s, %s)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET is_owner = EXCLUDED.is_owner, is_admin = EXCLUDED.is_admin RETURNING *""",
        (guild_uuid, user_uuid, is_owner, is_admin))
    assert row is not None
    return row


def user_has_guild_access(user_uuid: str, guild_discord_id: str) -> bool:
    row = _fetch_one("""SELECT gm.is_owner, gm.is_admin FROM guild_members gm
        JOIN guilds g ON g.id = gm.guild_id WHERE g.discord_id = %s AND gm.user_id = %s LIMIT 1""", (guild_discord_id, user_uuid))
    return bool(row and (row["is_owner"] or row["is_admin"]))


def get_user_guilds(user_uuid: str) -> list[dict[str, Any]]:
    rows = _fetch_all("""SELECT gm.is_owner, gm.is_admin, g.id, g.discord_id, g.name, g.icon, g.has_bot, g.owner_discord_id
        FROM guild_members gm JOIN guilds g ON g.id = gm.guild_id WHERE gm.user_id = %s""", (user_uuid,))
    return [{"id": str(row["discord_id"]), "guild_id": str(row["discord_id"]), "name": row["name"], "icon": row["icon"], "has_bot": row["has_bot"], "is_owner": row["is_owner"], "is_admin": row["is_admin"], "owner_id": str(row["owner_discord_id"]) if row["owner_discord_id"] else None} for row in rows]


def upsert_channels(guild_discord_id: str, channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guild = get_guild_by_discord_id(guild_discord_id)
    if not guild:
        raise DatabaseError("Guild has not yet been synchronized by the DailyBread bot.")
    sql = """INSERT INTO channels (guild_id, discord_id, name, channel_type, position, category_id, nsfw)
        VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (discord_id) DO UPDATE SET guild_id = EXCLUDED.guild_id,
        name = EXCLUDED.name, channel_type = EXCLUDED.channel_type, position = EXCLUDED.position, category_id = EXCLUDED.category_id, nsfw = EXCLUDED.nsfw RETURNING *"""
    try:
        with _pool().connection() as conn, conn.cursor() as cur:
            rows = []
            for channel in channels:
                cur.execute(sql, (guild["id"], channel["discord_id"], channel.get("name") or "unnamed", int(channel.get("channel_type", 0)), int(channel.get("position", 0)), channel.get("category_id"), bool(channel.get("nsfw", False))))
                rows.append(cur.fetchone())
            return rows
    except Exception as exc:
        LOGGER.exception("PostgreSQL channel synchronization failed")
        raise DatabaseError("Database operation failed.") from exc


def get_channel_by_discord_id(discord_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM channels WHERE discord_id = %s LIMIT 1", (discord_id,))


def upsert_roles(guild_discord_id: str, roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guild = get_guild_by_discord_id(guild_discord_id)
    if not guild:
        raise DatabaseError("Guild must exist before roles can be synchronized.")
    sql = """INSERT INTO roles (guild_id, discord_role_id, name, color, position, permissions) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (guild_id, discord_role_id) DO UPDATE SET name = EXCLUDED.name, color = EXCLUDED.color, position = EXCLUDED.position, permissions = EXCLUDED.permissions RETURNING *"""
    try:
        with _pool().connection() as conn, conn.cursor() as cur:
            rows = []
            for role in roles:
                cur.execute(sql, (guild["id"], role["discord_role_id"], role["name"], int(role.get("color", 0)), int(role.get("position", 0)), int(role.get("permissions", 0))))
                rows.append(cur.fetchone())
            return rows
    except Exception as exc:
        LOGGER.exception("PostgreSQL role synchronization failed")
        raise DatabaseError("Database operation failed.") from exc


def replace_member_roles(guild_member_id: str, role_ids: list[str]) -> None:
    try:
        with _pool().connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM member_roles WHERE guild_member_id = %s", (guild_member_id,))
            if role_ids:
                cur.executemany("INSERT INTO member_roles (guild_member_id, role_id) VALUES (%s, %s)", [(guild_member_id, role_id) for role_id in role_ids])
    except Exception as exc:
        LOGGER.exception("PostgreSQL member-role replacement failed")
        raise DatabaseError("Database operation failed.") from exc


def create_embed(creator_id: str, title: str, description: str, color: int | None = None, footer: str | None = None, image_url: str | None = None, thumbnail_url: str | None = None, author: str | None = None, message_content: str | None = None, verse_reference: str | None = None) -> dict[str, Any]:
    row = _fetch_one("""INSERT INTO embeds (creator_id, title, description, color, footer, image_url, thumbnail_url, author, message_content, verse_reference)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""", (creator_id, title or None, description or None, color, footer, image_url, thumbnail_url, author, message_content, verse_reference))
    assert row is not None
    return row


def get_embed_by_id(embed_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM embeds WHERE id = %s LIMIT 1", (embed_id,))


def list_embeds_for_user(user_uuid: str) -> list[dict[str, Any]]:
    return _fetch_all("SELECT * FROM embeds WHERE creator_id = %s ORDER BY created_at DESC", (user_uuid,))


def create_container(creator_id: str, name: str, data: dict[str, Any], guild_discord_id: str | None = None) -> dict[str, Any]:
    try:
        with _pool().connection() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO containers (creator_id, name, data) VALUES (%s, %s, %s) RETURNING *", (creator_id, name or "Untitled container", Jsonb(data)))
            container = cur.fetchone()
            if guild_discord_id:
                cur.execute("SELECT id FROM guilds WHERE discord_id = %s LIMIT 1", (guild_discord_id,))
                guild = cur.fetchone()
                if not guild:
                    raise DatabaseError("The selected guild has not been synchronized by the bot.")
                cur.execute("INSERT INTO guild_containers (guild_id, container_id) VALUES (%s, %s) ON CONFLICT (guild_id, container_id) DO NOTHING", (guild["id"], container["id"]))
            return container
    except DatabaseError:
        raise
    except Exception as exc:
        LOGGER.exception("PostgreSQL container creation failed")
        raise DatabaseError("Database operation failed.") from exc


def list_containers_for_user(user_uuid: str) -> list[dict[str, Any]]:
    return _fetch_all("""SELECT c.*, COALESCE(jsonb_agg(jsonb_build_object('guilds', jsonb_build_object('discord_id', g.discord_id)))
        FILTER (WHERE g.id IS NOT NULL), '[]'::jsonb) AS guild_containers FROM containers c
        LEFT JOIN guild_containers gc ON gc.container_id = c.id LEFT JOIN guilds g ON g.id = gc.guild_id
        WHERE c.creator_id = %s GROUP BY c.id ORDER BY c.created_at DESC""", (user_uuid,))


def get_container_for_user(container_id: str, user_uuid: str) -> Optional[dict[str, Any]]:
    rows = _fetch_all("""SELECT c.*, COALESCE(jsonb_agg(jsonb_build_object('guilds', jsonb_build_object('discord_id', g.discord_id)))
        FILTER (WHERE g.id IS NOT NULL), '[]'::jsonb) AS guild_containers FROM containers c
        LEFT JOIN guild_containers gc ON gc.container_id = c.id LEFT JOIN guilds g ON g.id = gc.guild_id
        WHERE c.id = %s AND c.creator_id = %s GROUP BY c.id ORDER BY c.created_at DESC""", (container_id, user_uuid))
    return rows[0] if rows else None


def create_webhook_record(webhook: dict[str, Any]) -> dict[str, Any]:
    row = _fetch_one("""SELECT g.id AS guild_id, c.id AS channel_id FROM guilds g JOIN channels c ON c.guild_id = g.id
        WHERE g.discord_id = %s AND c.discord_id = %s LIMIT 1""", (webhook["guild_id"], webhook["channel_id"]))
    if not row:
        raise DatabaseError("Webhook target is not synchronized by the bot.")
    result = _fetch_one("""INSERT INTO webhooks (guild_id, channel_id, discord_webhook_id, token, name, enabled)
        VALUES (%s, %s, %s, %s, %s, TRUE) ON CONFLICT (discord_webhook_id) DO UPDATE SET guild_id = EXCLUDED.guild_id,
        channel_id = EXCLUDED.channel_id, token = EXCLUDED.token, name = EXCLUDED.name, enabled = EXCLUDED.enabled RETURNING *""",
        (row["guild_id"], row["channel_id"], webhook["id"], webhook["token"], webhook.get("name") or "DailyBread"))
    assert result is not None
    return result


def _webhook_rows(filter_name: str, value: Any) -> list[dict[str, Any]]:
    queries = {
        "id": """SELECT w.*, c.discord_id AS channel_discord_id, c.name AS channel_name, g.discord_id AS guild_discord_id
            FROM webhooks w JOIN channels c ON c.id = w.channel_id JOIN guilds g ON g.id = w.guild_id
            WHERE w.discord_webhook_id = %s AND w.enabled = TRUE""",
        "channel": """SELECT w.*, c.discord_id AS channel_discord_id, c.name AS channel_name, g.discord_id AS guild_discord_id
            FROM webhooks w JOIN channels c ON c.id = w.channel_id JOIN guilds g ON g.id = w.guild_id
            WHERE w.channel_id = %s AND w.enabled = TRUE""",
        "guild": """SELECT w.*, c.discord_id AS channel_discord_id, c.name AS channel_name, g.discord_id AS guild_discord_id
            FROM webhooks w JOIN channels c ON c.id = w.channel_id JOIN guilds g ON g.id = w.guild_id
            WHERE w.guild_id = %s AND w.enabled = TRUE""",
    }
    return _fetch_all(queries[filter_name], (value,))


def _present_webhook(row: dict[str, Any]) -> dict[str, Any]:
    row["discord_id"] = str(row["discord_webhook_id"])
    row["channel_discord_id"] = str(row["channel_discord_id"])
    row["guild_discord_id"] = str(row["guild_discord_id"])
    return row


def get_webhook_by_id(webhook_discord_id: str) -> Optional[dict[str, Any]]:
    rows = _webhook_rows("id", webhook_discord_id)
    return _present_webhook(rows[0]) if rows else None


def get_webhooks_for_channel(channel_discord_id: str) -> list[dict[str, Any]]:
    channel = get_channel_by_discord_id(channel_discord_id)
    return [_present_webhook(row) for row in _webhook_rows("channel", channel["id"])] if channel else []


def get_webhooks_for_guild(guild_discord_id: str) -> list[dict[str, Any]]:
    guild = get_guild_by_discord_id(guild_discord_id)
    return [_present_webhook(row) for row in _webhook_rows("guild", guild["id"])] if guild else []


def delete_webhook(webhook_discord_id: str) -> None:
    _fetch_one("DELETE FROM webhooks WHERE discord_webhook_id = %s RETURNING id", (webhook_discord_id,))


def audit(action: str, guild_uuid: str | None = None, user_uuid: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    _fetch_one("INSERT INTO audit_logs (action, guild_id, user_id, metadata) VALUES (%s, %s, %s, %s) RETURNING id", (action, guild_uuid, user_uuid, Jsonb(metadata or {})))


def get_bible_cache(cache_key: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM bible_cache WHERE cache_key = %s LIMIT 1", (cache_key,))


def store_bible_cache(cache_key: str, reference: str, text: str, translation: str | None = None) -> dict[str, Any]:
    row = _fetch_one("""INSERT INTO bible_cache (cache_key, reference, text, translation) VALUES (%s, %s, %s, %s)
        ON CONFLICT (cache_key) DO UPDATE SET reference = EXCLUDED.reference, text = EXCLUDED.text, translation = EXCLUDED.translation RETURNING *""", (cache_key, reference, text, translation))
    assert row is not None
    return row
