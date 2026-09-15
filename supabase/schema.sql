-- ~/app_stack/db_init/init.sql

-- 1. Initialize Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Base Independent Tables (No Foreign Keys)
CREATE TABLE IF NOT EXISTS public.users (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    discord_id bigint NOT NULL,
    username text NOT NULL,
    global_name text NULL,
    avatar text NULL,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_discord_id_key UNIQUE (discord_id)
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.guilds (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    discord_id bigint NOT NULL,
    name text NOT NULL,
    icon text NULL,
    owner_discord_id bigint NULL,
    has_bot boolean NULL DEFAULT false,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT guilds_pkey PRIMARY KEY (id),
    CONSTRAINT guilds_discord_id_key UNIQUE (discord_id)
) TABLESPACE pg_default;

-- Added Placeholder for missing dependency table
CREATE TABLE IF NOT EXISTS public.roles (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    CONSTRAINT roles_pkey PRIMARY KEY (id)
) TABLESPACE pg_default;

-- 3. Dependent Tables (Level 1 Dependencies)
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    guild_id uuid NULL,
    user_id uuid NULL,
    action text NOT NULL,
    metadata jsonb NULL,
    created_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
    CONSTRAINT audit_logs_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES public.guilds (id) ON DELETE CASCADE,
    CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users (id) ON DELETE SET NULL
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.channels (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    guild_id uuid NOT NULL,
    discord_id bigint NOT NULL,
    name text NOT NULL,
    channel_type text NOT NULL,
    position integer NULL,
    category_id bigint NULL,
    nsfw boolean NULL DEFAULT false,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT channels_pkey PRIMARY KEY (id),
    CONSTRAINT channels_discord_id_key UNIQUE (discord_id),
    CONSTRAINT channels_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES public.guilds (id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.containers (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    creator_id uuid NULL,
    name text NOT NULL,
    data jsonb NOT NULL,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT containers_pkey PRIMARY KEY (id),
    CONSTRAINT containers_creator_id_fkey FOREIGN KEY (creator_id) REFERENCES public.users (id) ON DELETE SET NULL
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.embeds (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    creator_id uuid NULL,
    title text NULL,
    description text NULL,
    color text NULL,
    footer text NULL,
    image_url text NULL,
    thumbnail_url text NULL,
    author text NULL,
    timestamp boolean NULL DEFAULT false,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    message_content text NULL,
    verse_reference text NULL,
    CONSTRAINT embeds_pkey PRIMARY KEY (id),
    CONSTRAINT embeds_creator_id_fkey FOREIGN KEY (creator_id) REFERENCES public.users (id) ON DELETE SET NULL
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.guild_members (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    guild_id uuid NOT NULL,
    user_id uuid NOT NULL,
    is_owner boolean NULL DEFAULT false,
    is_admin boolean NULL DEFAULT false,
    joined_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT guild_members_pkey PRIMARY KEY (id),
    CONSTRAINT guild_members_guild_id_user_id_key UNIQUE (guild_id, user_id),
    CONSTRAINT guild_members_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES public.guilds (id) ON DELETE CASCADE,
    CONSTRAINT guild_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users (id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.guild_settings (
    guild_id uuid NOT NULL,
    timezone text NULL DEFAULT 'UTC'::text,
    default_translation text NULL,
    language text NULL DEFAULT 'en'::text,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT guild_settings_pkey PRIMARY KEY (guild_id),
    CONSTRAINT guild_settings_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES public.guilds (id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.oauth_sessions (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    access_token text NOT NULL,
    refresh_token text NOT NULL,
    expires_at timestamp without time zone NULL,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT oauth_sessions_pkey PRIMARY KEY (id),
    CONSTRAINT oauth_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users (id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- 4. Many-to-Many Relational Tables (Level 2 Dependencies)
CREATE TABLE IF NOT EXISTS public.guild_containers (
    guild_id uuid NOT NULL,
    container_id uuid NOT NULL,
    CONSTRAINT guild_containers_pkey PRIMARY KEY (guild_id, container_id),
    CONSTRAINT guild_containers_container_id_fkey FOREIGN KEY (container_id) REFERENCES public.containers (id) ON DELETE CASCADE,
    CONSTRAINT guild_containers_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES public.guilds (id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE TABLE IF NOT EXISTS public.member_roles (
    guild_member_id uuid NOT NULL,
    role_id uuid NOT NULL,
    CONSTRAINT member_roles_pkey PRIMARY KEY (guild_member_id, role_id),
    CONSTRAINT member_roles_guild_member_id_fkey FOREIGN KEY (guild_member_id) REFERENCES public.guild_members (id) ON DELETE CASCADE,
    CONSTRAINT member_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles (id) ON DELETE CASCADE
) TABLESPACE pg_default;


– 5. Other
CREATE TABLE IF NOT EXISTS public.bible_cache ( id uuid NOT NULL DEFAULT gen_random_uuid(), reference text NOT NULL, language text NULL DEFAULT 'en'::text, text text NOT NULL, translation text NULL, updated_at timestamp without time zone NULL DEFAULT now(), cache_key text NOT NULL, CONSTRAINT bible_cache_pkey PRIMARY KEY (id), CONSTRAINT bible_cache_cache_key_unique UNIQUE (cache_key) ) TABLESPACE pg_default; 

CREATE TABLE IF NOT EXISTS public.webhooks (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    guild_id uuid NOT NULL,
    channel_id uuid NULL,
    discord_webhook_id bigint NULL,
    token text NULL,
    name text NULL,
    enabled boolean NULL DEFAULT true,
    created_at timestamp without time zone NULL DEFAULT now(),
    updated_at timestamp without time zone NULL DEFAULT now(),
    CONSTRAINT webhooks_pkey PRIMARY KEY (id),
    CONSTRAINT webhooks_discord_webhook_id_key UNIQUE (discord_webhook_id),
    CONSTRAINT webhooks_channel_id_fkey
        FOREIGN KEY (channel_id)
        REFERENCES public.channels (id)
        ON DELETE CASCADE,
    CONSTRAINT webhooks_guild_id_fkey
        FOREIGN KEY (guild_id)
        REFERENCES public.guilds (id)
        ON DELETE CASCADE
) TABLESPACE pg_default;