"""Regression checks for the DailyBread v2 Supabase rebuild.

These tests are intentionally local and read-only: they validate the versioned
schema and synchronization boundaries without requiring live Discord/OAuth data.
"""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8").lower()
LOGIN_FLOW = (ROOT / "backend" / "main.py").read_text(encoding="utf-8").lower()
BOT_TREES = [
    ast.parse(path.read_text(encoding="utf-8"))
    for path in (ROOT / "bot").rglob("*.py")
]


def test_v2_schema_contains_all_required_tables_and_preserves_bible_cache() -> None:
    required_tables = {
        "users",
        "oauth_sessions",
        "guilds",
        "guild_members",
        "roles",
        "member_roles",
        "channels",
        "webhooks",
        "embeds",
        "guild_embeds",
        "containers",
        "guild_containers",
        "guild_settings",
        "audit_logs",
        "notifications",
    }

    for table in required_tables:
        assert f"create table public.{table} (" in SCHEMA

    # bible_cache is pre-existing application data and must not be rebuilt.
    assert "create table public.bible_cache" not in SCHEMA
    assert "drop table" not in SCHEMA


def test_v2_schema_uses_uuid_relationships_and_discord_snowflake_uniqueness() -> None:
    assert "id uuid primary key default gen_random_uuid()" in SCHEMA
    assert "discord_id bigint not null unique" in SCHEMA
    assert "guild_id uuid not null references public.guilds(id)" in SCHEMA
    assert "user_id uuid not null references public.users(id)" in SCHEMA
    assert "channel_id uuid not null references public.channels(id)" in SCHEMA
    assert "creator_id uuid not null references public.users(id)" in SCHEMA
    assert "unique (guild_id, user_id)" in SCHEMA
    assert "unique (guild_id, discord_role_id)" in SCHEMA


def test_schema_has_indexes_for_high_volume_lookup_paths() -> None:
    expected_indexes = {
        "guild_members_user_id_idx",
        "channels_guild_id_idx",
        "webhooks_guild_id_idx",
        "webhooks_channel_id_idx",
        "roles_guild_id_idx",
        "oauth_sessions_user_id_idx",
        "audit_logs_guild_created_idx",
        "notifications_user_unread_idx",
        "embeds_creator_created_idx",
        "containers_creator_created_idx",
    }
    for index in expected_indexes:
        assert f"create index {index}" in SCHEMA


def test_bot_has_no_supabase_access() -> None:
    imported_modules = {
        alias.name
        for tree in BOT_TREES
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules |= {
        node.module or ""
        for tree in BOT_TREES
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    executable_names = {
        node.id
        for tree in BOT_TREES
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }

    assert not any("supabase" in module for module in imported_modules)
    assert "supabase_service" not in executable_names
    assert "create_client" not in executable_names


def test_login_flow_is_the_guild_sync_boundary() -> None:
    assert "a website login is the only event that updates supabase" in LOGIN_FLOW
    assert "supabase_service.upsert_guild(" in LOGIN_FLOW
    assert "supabase_service.upsert_guild_member(" in LOGIN_FLOW
    assert "supabase_service.upsert_channels(" in LOGIN_FLOW
