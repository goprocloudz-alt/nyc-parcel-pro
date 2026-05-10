-- NYC Parcel Pro — initial schema for NYC-data tables.
-- Applied automatically by docker-compose on first container start
-- (mounted at /docker-entrypoint-initdb.d/).
--
-- Scope: extensions, shared trigger, properties, sync_log.
-- agencies and users are managed by Prisma Migrate (apps/web/prisma/).
-- NEVER edit this file after it has been applied — create a new migration instead
-- (CLAUDE.md rule 2).

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS postgis;    -- geometry types + spatial indexes
CREATE EXTENSION IF NOT EXISTS citext;     -- case-insensitive TEXT (used by Prisma migration for users.email)
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ── Shared trigger function ───────────────────────────────────────────────────
-- Belt-and-suspenders for updated_at: Prisma's @updatedAt handles app-layer
-- writes; this trigger covers any psycopg / direct-SQL writes from the ETL.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── properties (PLUTO 64uk-42ks) ─────────────────────────────────────────────
-- Master parcel record for all five boroughs. ~870k rows, refreshed quarterly
-- via full staging-table swap (ETL.md §5). Written by ETL, read by web app.
CREATE TABLE properties (
  bbl                CHAR(10)    PRIMARY KEY,      -- zero-padded; always a string (CLAUDE.md rule 8)
  borough            CHAR(2)     NOT NULL,          -- MN BX BK QN SI
  block              INTEGER     NOT NULL,
  lot                INTEGER     NOT NULL,
  cd                 INTEGER,                       -- community district
  council_district   INTEGER,
  zip_code           CHAR(5),
  address            TEXT,
  owner_name         TEXT,

  -- Areas (sq ft)
  lot_area           INTEGER,
  bldg_area          INTEGER,
  com_area           INTEGER,
  res_area           INTEGER,
  office_area        INTEGER,
  retail_area        INTEGER,
  garage_area        INTEGER,
  storage_area       INTEGER,
  factory_area       INTEGER,
  other_area         INTEGER,

  -- Building characteristics
  num_bldgs          INTEGER,
  num_floors         NUMERIC(5,2),
  units_res          INTEGER,
  units_total        INTEGER,
  year_built         INTEGER,
  year_alter1        INTEGER,
  year_alter2        INTEGER,
  bldg_class         CHAR(2),
  land_use           CHAR(2),

  -- Lot dimensions
  lot_front          NUMERIC(8,2),
  lot_depth          NUMERIC(8,2),
  bldg_front         NUMERIC(8,2),
  bldg_depth         NUMERIC(8,2),

  -- Zoning
  zone_dist1         TEXT,
  zone_dist2         TEXT,
  zone_dist3         TEXT,
  zone_dist4         TEXT,
  overlay1           TEXT,
  overlay2           TEXT,
  spec_dist1         TEXT,
  spec_dist2         TEXT,
  ltd_height         TEXT,
  split_zone         BOOLEAN,

  -- Floor area ratios
  resid_far          NUMERIC(6,2),
  comm_far           NUMERIC(6,2),
  facil_far          NUMERIC(6,2),
  built_far          NUMERIC(6,2),

  -- Assessment (most recent fiscal year)
  assess_land        NUMERIC(14,2),
  assess_tot         NUMERIC(14,2),
  exempt_tot         NUMERIC(14,2),

  -- Misc
  landmark           TEXT,
  easements          INTEGER,
  owner_type         CHAR(1),
  hist_dist          TEXT,

  -- Geospatial (WGS84 per SCHEMA.md §1; distance math uses SRID 2263)
  latitude           NUMERIC(10,7),
  longitude          NUMERIC(10,7),
  geom               GEOMETRY(MultiPolygon, 4326),

  -- Provenance (required on every NYC-data table — SCHEMA.md §2)
  pluto_version      TEXT        NOT NULL,           -- e.g. "25v4"
  source_dataset     TEXT        NOT NULL DEFAULT '64uk-42ks',
  last_synced_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_properties_borough_block_lot ON properties(borough, block, lot);
CREATE INDEX idx_properties_zip               ON properties(zip_code);
CREATE INDEX idx_properties_bldg_class        ON properties(bldg_class);
CREATE INDEX idx_properties_geom              ON properties USING gist(geom);
-- GIN indexes for full-text search (PROJECT.md story #1: search by address/owner)
CREATE INDEX idx_properties_owner   ON properties USING gin(to_tsvector('simple', owner_name));
CREATE INDEX idx_properties_address ON properties USING gin(to_tsvector('simple', address));

-- ── sync_log (SCHEMA.md §3.5) ─────────────────────────────────────────────────
-- ETL run audit. Written exclusively by the Python ETL worker via psycopg.
CREATE TABLE sync_log (
  id             BIGSERIAL   PRIMARY KEY,
  dataset_id     TEXT        NOT NULL,    -- Socrata dataset ID e.g. "64uk-42ks"
  dataset_name   TEXT        NOT NULL,    -- human-readable e.g. "PLUTO"
  started_at     TIMESTAMPTZ NOT NULL,
  completed_at   TIMESTAMPTZ,
  rows_fetched   INTEGER,
  rows_upserted  INTEGER,
  rows_deleted   INTEGER,
  status         TEXT        NOT NULL,    -- running | success | failed
  error_message  TEXT,
  high_watermark TIMESTAMPTZ,             -- max(:updated_at) seen in this run
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sync_log_dataset ON sync_log(dataset_id, started_at DESC);
