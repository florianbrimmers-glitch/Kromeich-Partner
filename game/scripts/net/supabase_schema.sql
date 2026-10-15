-- Kromeich Heroes: Supabase-Schema fuer asynchronen Multiplayer.
--
-- Anwenden:
--   1. Supabase-Projekt erstellen (supabase.com / neues Projekt)
--   2. SQL Editor -> dieses Skript einfuegen und ausfuehren
--   3. Auth: Email + Magic Link aktivieren unter Authentication > Providers
--   4. ENV-Variablen fuer den Client: SUPABASE_URL, SUPABASE_ANON_KEY
--
-- RLS-Regeln sind defensiv: Spieler sehen nur ihre eigenen Matches und Zuege.

-- ========================================================================
-- Extensions
-- ========================================================================

create extension if not exists "uuid-ossp";

-- ========================================================================
-- Tabellen
-- ========================================================================

-- Spielerprofil (spiegelt auth.users)
create table if not exists public.players (
    id uuid primary key references auth.users on delete cascade,
    display_name text not null,
    created_at timestamptz not null default now()
);

-- Ein Match zwischen 2-4 Spielern.
-- state_json enthaelt den kanonischen Spielzustand (Helden, Staedte, Ressourcen, Karte-Seed).
create table if not exists public.matches (
    id uuid primary key default uuid_generate_v4(),
    host_id uuid not null references public.players on delete cascade,
    map_template text not null,
    map_seed bigint not null,
    turn int not null default 1,
    current_player_slot int not null default 0,
    state_json jsonb not null,
    status text not null default 'active' check (status in ('active', 'finished', 'abandoned')),
    winner_player_id uuid references public.players,
    turn_deadline timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Teilnahme-Tabelle (Many-to-Many Match <-> Player)
create table if not exists public.match_players (
    match_id uuid not null references public.matches on delete cascade,
    player_id uuid not null references public.players on delete cascade,
    slot int not null check (slot between 0 and 3),
    faction text not null,
    color text not null,
    primary key (match_id, player_id),
    unique (match_id, slot)
);

-- Unveraenderliche Zug-Historie (fuer Replay & Audit)
create table if not exists public.moves (
    id uuid primary key default uuid_generate_v4(),
    match_id uuid not null references public.matches on delete cascade,
    turn int not null,
    player_id uuid not null references public.players,
    slot int not null,
    action_json jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists moves_match_turn_idx on public.moves(match_id, turn);
create index if not exists matches_host_idx on public.matches(host_id);
create index if not exists matches_status_updated_idx on public.matches(status, updated_at desc);

-- ========================================================================
-- Row-Level Security
-- ========================================================================

alter table public.players enable row level security;
alter table public.matches enable row level security;
alter table public.match_players enable row level security;
alter table public.moves enable row level security;

-- players: jeder sieht sich selbst; man kann sein eigenes Profil updaten
drop policy if exists "players_self_read" on public.players;
create policy "players_self_read" on public.players
    for select using (true);
drop policy if exists "players_self_upsert" on public.players;
create policy "players_self_upsert" on public.players
    for all using (auth.uid() = id) with check (auth.uid() = id);

-- matches: nur Teilnehmer sehen das Match
drop policy if exists "matches_participants_read" on public.matches;
create policy "matches_participants_read" on public.matches
    for select using (
        exists (select 1 from public.match_players mp
                where mp.match_id = matches.id and mp.player_id = auth.uid())
    );

-- matches: nur Host erstellt, nur Host updated (wir validieren in Edge Fn)
drop policy if exists "matches_host_write" on public.matches;
create policy "matches_host_write" on public.matches
    for all using (host_id = auth.uid()) with check (host_id = auth.uid());

-- match_players: Teilnehmer sehen alle Slots; Host fuegt Spieler hinzu
drop policy if exists "mp_participants_read" on public.match_players;
create policy "mp_participants_read" on public.match_players
    for select using (
        exists (select 1 from public.match_players mp
                where mp.match_id = match_players.match_id and mp.player_id = auth.uid())
    );
drop policy if exists "mp_host_write" on public.match_players;
create policy "mp_host_write" on public.match_players
    for all using (
        exists (select 1 from public.matches m
                where m.id = match_players.match_id and m.host_id = auth.uid())
    );

-- moves: Teilnehmer lesen; nur der Zugspieler schreibt seine eigenen Zuege
drop policy if exists "moves_participants_read" on public.moves;
create policy "moves_participants_read" on public.moves
    for select using (
        exists (select 1 from public.match_players mp
                where mp.match_id = moves.match_id and mp.player_id = auth.uid())
    );
drop policy if exists "moves_own_write" on public.moves;
create policy "moves_own_write" on public.moves
    for insert with check (player_id = auth.uid());

-- ========================================================================
-- Trigger: updated_at
-- ========================================================================

create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end $$;

drop trigger if exists matches_touch on public.matches;
create trigger matches_touch
    before update on public.matches
    for each row execute function public.touch_updated_at();

-- ========================================================================
-- Realtime: Aktiviert Channels fuer matches und moves
-- ========================================================================

-- In der Supabase-Console zu aktivieren:
--   Database > Replication > enable: matches, moves, match_players
