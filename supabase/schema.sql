-- DailyBread v2: existing PostgreSQL schema. This file is not applied by the application.
-- This deliberately does not migrate or retain the legacy DailyBread tables.
create extension if not exists pgcrypto;

create or replace function public.set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = timezone('utc', now()); return new; end $$;

create table public.users (
  id uuid primary key default gen_random_uuid(),
  discord_id bigint not null unique,
  username text not null,
  global_name text,
  avatar text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create table public.oauth_sessions (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references public.users(id) on delete cascade,
  access_token text not null, refresh_token text, expires_at timestamptz not null,
  created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now())
);
create table public.guilds (
  id uuid primary key default gen_random_uuid(), discord_id bigint not null unique, name text not null, icon text,
  owner_discord_id bigint, has_bot boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now())
);
create table public.guild_members (
  id uuid primary key default gen_random_uuid(), guild_id uuid not null references public.guilds(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade, is_owner boolean not null default false,
  is_admin boolean not null default false, joined_at timestamptz not null default timezone('utc', now()), unique (guild_id, user_id)
);
create table public.roles (
  id uuid primary key default gen_random_uuid(), guild_id uuid not null references public.guilds(id) on delete cascade,
  discord_role_id bigint not null, name text not null, color integer not null default 0, position integer not null default 0,
  permissions bigint not null default 0, created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now()),
  unique (guild_id, discord_role_id)
);
create table public.member_roles (
  guild_member_id uuid not null references public.guild_members(id) on delete cascade,
  role_id uuid not null references public.roles(id) on delete cascade, primary key (guild_member_id, role_id)
);
create table public.channels (
  id uuid primary key default gen_random_uuid(), guild_id uuid not null references public.guilds(id) on delete cascade,
  discord_id bigint not null unique, name text not null, channel_type integer not null, position integer not null default 0,
  category_id bigint, nsfw boolean not null default false, created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now())
);
create table public.webhooks (
  id uuid primary key default gen_random_uuid(), guild_id uuid not null references public.guilds(id) on delete cascade,
  channel_id uuid not null references public.channels(id) on delete cascade, discord_webhook_id bigint not null unique,
  token text not null, name text not null, enabled boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now())
);
create table public.embeds (
  id uuid primary key default gen_random_uuid(), creator_id uuid not null references public.users(id) on delete cascade,
  title text, description text, color integer, footer text, image_url text, thumbnail_url text, author text, timestamp timestamptz,
  message_content text, verse_reference text,
  created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now())
);
create table public.guild_embeds (guild_id uuid not null references public.guilds(id) on delete cascade, embed_id uuid not null references public.embeds(id) on delete cascade, primary key (guild_id, embed_id));
create table public.containers (id uuid primary key default gen_random_uuid(), creator_id uuid not null references public.users(id) on delete cascade, name text not null, data jsonb not null, created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now()));
create table public.guild_containers (guild_id uuid not null references public.guilds(id) on delete cascade, container_id uuid not null references public.containers(id) on delete cascade, primary key (guild_id, container_id));
create table public.guild_settings (guild_id uuid primary key references public.guilds(id) on delete cascade, timezone text not null default 'UTC', default_translation text, language text not null default 'en', created_at timestamptz not null default timezone('utc', now()), updated_at timestamptz not null default timezone('utc', now()));
create table public.audit_logs (id uuid primary key default gen_random_uuid(), guild_id uuid references public.guilds(id) on delete set null, user_id uuid references public.users(id) on delete set null, action text not null, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default timezone('utc', now()));
create table public.notifications (id uuid primary key default gen_random_uuid(), user_id uuid not null references public.users(id) on delete cascade, title text not null, message text not null, read boolean not null default false, created_at timestamptz not null default timezone('utc', now()));

create index guild_members_user_id_idx on public.guild_members(user_id);
create index channels_guild_id_idx on public.channels(guild_id);
create index webhooks_guild_id_idx on public.webhooks(guild_id);
create index webhooks_channel_id_idx on public.webhooks(channel_id);
create index roles_guild_id_idx on public.roles(guild_id);
create index oauth_sessions_user_id_idx on public.oauth_sessions(user_id);
create index audit_logs_guild_created_idx on public.audit_logs(guild_id, created_at desc);
create index notifications_user_unread_idx on public.notifications(user_id, read, created_at desc);
create index embeds_creator_created_idx on public.embeds(creator_id, created_at desc);
create index containers_creator_created_idx on public.containers(creator_id, created_at desc);

create trigger users_updated_at before update on public.users for each row execute function public.set_updated_at();
create trigger oauth_sessions_updated_at before update on public.oauth_sessions for each row execute function public.set_updated_at();
create trigger guilds_updated_at before update on public.guilds for each row execute function public.set_updated_at();
create trigger roles_updated_at before update on public.roles for each row execute function public.set_updated_at();
create trigger channels_updated_at before update on public.channels for each row execute function public.set_updated_at();
create trigger webhooks_updated_at before update on public.webhooks for each row execute function public.set_updated_at();
create trigger embeds_updated_at before update on public.embeds for each row execute function public.set_updated_at();
create trigger containers_updated_at before update on public.containers for each row execute function public.set_updated_at();
create trigger guild_settings_updated_at before update on public.guild_settings for each row execute function public.set_updated_at();
