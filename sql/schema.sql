-- Run this in Supabase's SQL editor (Project -> SQL Editor -> New query)

create table if not exists nepse_live_prices (
    symbol text primary key,
    ltp numeric,
    point_change numeric,
    percent_change numeric,
    total_qty numeric,
    updated_at timestamptz default now()
);

-- Single-row table for overall market status
create table if not exists nepse_market_status (
    id int primary key default 1,
    is_open boolean,
    updated_at timestamptz default now(),
    constraint single_row check (id = 1)
);
insert into nepse_market_status (id, is_open) values (1, false)
    on conflict (id) do nothing;

-- Allow public read-only access (frontend uses the anon key to read)
alter table nepse_live_prices enable row level security;
alter table nepse_market_status enable row level security;

create policy "Public read access" on nepse_live_prices
    for select using (true);
create policy "Public read access" on nepse_market_status
    for select using (true);

-- No insert/update/delete policy for the anon key on purpose —
-- only the service_role key (used by the scraper, kept secret) can write.
