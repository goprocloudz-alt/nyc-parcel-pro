# NYC Parcel Pro — Database Schema

**Database:** PostgreSQL 16 with PostGIS 3.4
**Naming:** snake_case, plural table names, `id` for surrogate PKs, `bbl` as the universal NYC parcel key (10-char string: `B BBBBB LLLL`)

---

## 1. Conventions

- **BBL** is the join key across nearly every NYC dataset. Store as `CHAR(10)` (zero-padded). Example: `1000160001`.
- All NYC-data tables include:
  - `last_synced_at TIMESTAMPTZ NOT NULL` — when this row was last refreshed from source
  - `source_dataset TEXT NOT NULL` — Socrata dataset ID (e.g., `64uk-42ks` for PLUTO)
- All app tables include `created_at` and `updated_at` (auto-managed via trigger).
- Money is stored as `NUMERIC(14,2)` — never floats.
- Geometry uses SRID 4326 (WGS84) for the API layer; cast to 2263 (NY State Plane) for distance math.
- Soft delete via `deleted_at TIMESTAMPTZ NULL` on app tables. NYC-data tables are hard-deleted on full refresh.

---

## 2. NYC data tables (refreshed by ETL)

### 2.1 `properties` — master parcel record (from PLUTO 64uk-42ks)

```sql
CREATE TABLE properties (
  bbl                CHAR(10) PRIMARY KEY,
  borough            CHAR(2) NOT NULL,         -- MN, BX, BK, QN, SI
  block              INTEGER NOT NULL,
  lot                INTEGER NOT NULL,
  cd                 INTEGER,                  -- community district
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

  -- Building info
  num_bldgs          INTEGER,
  num_floors         NUMERIC(5,2),
  units_res          INTEGER,
  units_total        INTEGER,
  year_built         INTEGER,
  year_alter1        INTEGER,
  year_alter2        INTEGER,
  bldg_class         CHAR(2),
  land_use           CHAR(2),

  -- Lot
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

  -- FAR
  resid_far          NUMERIC(6,2),
  comm_far           NUMERIC(6,2),
  facil_far          NUMERIC(6,2),
  built_far          NUMERIC(6,2),

  -- Assessment (most recent FY)
  assess_land        NUMERIC(14,2),
  assess_tot         NUMERIC(14,2),
  exempt_tot         NUMERIC(14,2),

  -- Misc
  landmark           TEXT,
  easements          INTEGER,
  owner_type         CHAR(1),
  hist_dist          TEXT,

  -- Geo
  latitude           NUMERIC(10,7),
  longitude          NUMERIC(10,7),
  geom               GEOMETRY(MultiPolygon, 4326),

  -- Provenance
  pluto_version      TEXT NOT NULL,            -- e.g., "25v4"
  source_dataset     TEXT NOT NULL DEFAULT '64uk-42ks',
  last_synced_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_properties_borough_block_lot ON properties(borough, block, lot);
CREATE INDEX idx_properties_zip ON properties(zip_code);
CREATE INDEX idx_properties_owner ON properties USING gin (to_tsvector('simple', owner_name));
CREATE INDEX idx_properties_address ON properties USING gin (to_tsvector('simple', address));
CREATE INDEX idx_properties_geom ON properties USING gist(geom);
CREATE INDEX idx_properties_bldg_class ON properties(bldg_class);
```

### 2.2 `acris_master` — deed/mortgage document headers (bnx9-e6tj)

```sql
CREATE TABLE acris_master (
  document_id        CHAR(16) PRIMARY KEY,
  record_type        CHAR(1) NOT NULL,
  crfn               TEXT,
  recorded_borough   INTEGER,
  doc_type           TEXT,                     -- DEED, MTGE, AGMT, etc.
  document_date      DATE,
  document_amt       NUMERIC(14,2),
  recorded_datetime  TIMESTAMPTZ,
  modified_date      TIMESTAMPTZ,
  reel_yr            INTEGER,
  reel_nbr           INTEGER,
  reel_pg            INTEGER,
  percent_trans      NUMERIC(6,4),
  good_through_date  DATE,
  source_dataset     TEXT NOT NULL DEFAULT 'bnx9-e6tj',
  last_synced_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_acris_master_doc_type ON acris_master(doc_type);
CREATE INDEX idx_acris_master_doc_date ON acris_master(document_date);
```

### 2.3 `acris_legals` — links documents to BBLs (8h5j-fqxa)

```sql
CREATE TABLE acris_legals (
  id                 BIGSERIAL PRIMARY KEY,
  document_id        CHAR(16) NOT NULL,
  borough            INTEGER NOT NULL,
  block              INTEGER NOT NULL,
  lot                INTEGER NOT NULL,
  bbl                CHAR(10) GENERATED ALWAYS AS (
                       LPAD(borough::text, 1, '0') ||
                       LPAD(block::text,   5, '0') ||
                       LPAD(lot::text,     4, '0')
                     ) STORED,
  easement           BOOLEAN,
  partial_lot        TEXT,
  air_rights         BOOLEAN,
  subterranean_rights BOOLEAN,
  property_type      TEXT,
  street_number      TEXT,
  street_name        TEXT,
  unit_number        TEXT,
  source_dataset     TEXT NOT NULL DEFAULT '8h5j-fqxa',
  last_synced_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_acris_legals_bbl ON acris_legals(bbl);
CREATE INDEX idx_acris_legals_doc ON acris_legals(document_id);
```

### 2.4 `acris_parties` — buyers/sellers/banks (636b-3b5g)

```sql
CREATE TABLE acris_parties (
  id                 BIGSERIAL PRIMARY KEY,
  document_id        CHAR(16) NOT NULL,
  party_type         INTEGER,                  -- 1=grantor, 2=grantee, 3=lender
  name               TEXT,
  address_1          TEXT,
  address_2          TEXT,
  country            TEXT,
  city               TEXT,
  state              TEXT,
  zip                TEXT,
  source_dataset     TEXT NOT NULL DEFAULT '636b-3b5g',
  last_synced_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_acris_parties_doc ON acris_parties(document_id);
CREATE INDEX idx_acris_parties_name ON acris_parties USING gin (to_tsvector('simple', name));
```

### 2.5 `dof_sales` — annualized rolling sales (DOF)

```sql
CREATE TABLE dof_sales (
  id                 BIGSERIAL PRIMARY KEY,
  bbl                CHAR(10) NOT NULL,
  borough            INTEGER,
  neighborhood       TEXT,
  building_class_category TEXT,
  tax_class_present  TEXT,
  block              INTEGER,
  lot                INTEGER,
  bldg_class_present CHAR(2),
  address            TEXT,
  apt_number         TEXT,
  zip_code           CHAR(5),
  units_res          INTEGER,
  units_com          INTEGER,
  units_total        INTEGER,
  land_sqft          INTEGER,
  gross_sqft         INTEGER,
  year_built         INTEGER,
  tax_class_at_sale  TEXT,
  bldg_class_at_sale CHAR(2),
  sale_price         NUMERIC(14,2),
  sale_date          DATE NOT NULL,
  source_dataset     TEXT NOT NULL,
  last_synced_at     TIMESTAMPTZ NOT NULL,
  UNIQUE (bbl, sale_date, sale_price, address)
);

CREATE INDEX idx_dof_sales_bbl ON dof_sales(bbl);
CREATE INDEX idx_dof_sales_date ON dof_sales(sale_date DESC);
CREATE INDEX idx_dof_sales_class ON dof_sales(bldg_class_at_sale);
```

### 2.6 `dob_permits` (ipu4-2q9a) and `dob_violations` (3h2n-5cm9)

```sql
CREATE TABLE dob_permits (
  job_filing_number  TEXT PRIMARY KEY,
  bbl                CHAR(10),
  borough            TEXT,
  house_number       TEXT,
  street_name        TEXT,
  job_type           TEXT,
  permit_status      TEXT,
  filing_date        DATE,
  issuance_date      DATE,
  expiration_date    DATE,
  work_type          TEXT,
  permittee_business_name TEXT,
  source_dataset     TEXT NOT NULL DEFAULT 'ipu4-2q9a',
  last_synced_at     TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_dob_permits_bbl ON dob_permits(bbl);

CREATE TABLE dob_violations (
  isn_dob_bis_viol   TEXT PRIMARY KEY,
  bbl                CHAR(10),
  borough            CHAR(1),
  block              TEXT,
  lot                TEXT,
  issue_date         DATE,
  violation_type     TEXT,
  violation_category TEXT,
  description        TEXT,
  disposition_date   DATE,
  ecb_number         TEXT,
  source_dataset     TEXT NOT NULL DEFAULT '3h2n-5cm9',
  last_synced_at     TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_dob_viol_bbl ON dob_violations(bbl);
```

### 2.7 `hpd_violations` (wvxf-dwi5) and `hpd_registrations` (tesw-yqqr)

```sql
CREATE TABLE hpd_violations (
  violation_id       BIGINT PRIMARY KEY,
  building_id        BIGINT,
  registration_id    BIGINT,
  bbl                CHAR(10),
  borough            TEXT,
  house_number       TEXT,
  street_name        TEXT,
  apartment          TEXT,
  story              TEXT,
  inspection_date    DATE,
  approved_date      DATE,
  original_cert_by_date DATE,
  current_status     TEXT,
  current_status_date DATE,
  novissueddate      DATE,
  novdescription     TEXT,
  class              CHAR(1),                  -- A, B, C, I
  source_dataset     TEXT NOT NULL DEFAULT 'wvxf-dwi5',
  last_synced_at     TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_hpd_viol_bbl ON hpd_violations(bbl);
CREATE INDEX idx_hpd_viol_status ON hpd_violations(current_status);

CREATE TABLE hpd_registrations (
  registration_id    BIGINT PRIMARY KEY,
  building_id        BIGINT,
  bbl                CHAR(10),
  borough            TEXT,
  house_number       TEXT,
  street_name        TEXT,
  zip                CHAR(5),
  registration_end_date DATE,
  last_registration_date DATE,
  source_dataset     TEXT NOT NULL DEFAULT 'tesw-yqqr',
  last_synced_at     TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_hpd_reg_bbl ON hpd_registrations(bbl);
```

### 2.8 `complaints_311` (erm2-nwe9, filtered to housing/building)

```sql
CREATE TABLE complaints_311 (
  unique_key         BIGINT PRIMARY KEY,
  bbl                CHAR(10),
  created_date       TIMESTAMPTZ,
  closed_date        TIMESTAMPTZ,
  agency             TEXT,
  complaint_type     TEXT,
  descriptor         TEXT,
  status             TEXT,
  resolution_description TEXT,
  borough            TEXT,
  incident_address   TEXT,
  zip                CHAR(5),
  latitude           NUMERIC(10,7),
  longitude          NUMERIC(10,7),
  source_dataset     TEXT NOT NULL DEFAULT 'erm2-nwe9',
  last_synced_at     TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_311_bbl ON complaints_311(bbl);
CREATE INDEX idx_311_created ON complaints_311(created_date DESC);
```

### 2.9 `housing_litigations` (59kj-ewme), `evictions`, `rent_stabilization`

Standard schemas — see individual Socrata dataset metadata. Each carries `bbl`, key dates, and the two provenance columns.

---

## 3. Application tables

### 3.1 Tenancy & users

```sql
CREATE TABLE agencies (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name               TEXT NOT NULL,
  logo_url           TEXT,
  plan               TEXT NOT NULL DEFAULT 'pilot',
  brand_color        TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at         TIMESTAMPTZ
);

CREATE TABLE users (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id          UUID NOT NULL REFERENCES agencies(id),
  email              CITEXT NOT NULL UNIQUE,
  password_hash      TEXT,
  full_name          TEXT,
  role               TEXT NOT NULL DEFAULT 'agent',  -- admin | agent
  email_verified_at  TIMESTAMPTZ,
  last_login_at      TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at         TIMESTAMPTZ
);
CREATE INDEX idx_users_agency ON users(agency_id);
```

### 3.2 Watchlists & saved searches

```sql
CREATE TABLE watchlists (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id          UUID NOT NULL REFERENCES agencies(id),
  owner_user_id      UUID NOT NULL REFERENCES users(id),
  name               TEXT NOT NULL,
  scope              TEXT NOT NULL DEFAULT 'private',  -- private | agency
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE watchlist_items (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  watchlist_id       UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
  bbl                CHAR(10) NOT NULL,
  notes              TEXT,
  added_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (watchlist_id, bbl)
);
CREATE INDEX idx_wl_items_bbl ON watchlist_items(bbl);

CREATE TABLE saved_searches (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id      UUID NOT NULL REFERENCES users(id),
  agency_id          UUID NOT NULL REFERENCES agencies(id),
  name               TEXT NOT NULL,
  criteria           JSONB NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.3 Alerts

```sql
CREATE TABLE alert_subscriptions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL REFERENCES users(id),
  watchlist_item_id  UUID REFERENCES watchlist_items(id) ON DELETE CASCADE,
  saved_search_id    UUID REFERENCES saved_searches(id) ON DELETE CASCADE,
  channel            TEXT NOT NULL,                   -- email | sms | webhook
  trigger_types      TEXT[] NOT NULL,                 -- {deed,permit,violation,complaint}
  active             BOOLEAN NOT NULL DEFAULT TRUE,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (watchlist_item_id IS NOT NULL OR saved_search_id IS NOT NULL)
);

CREATE TABLE alert_events (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id    UUID NOT NULL REFERENCES alert_subscriptions(id) ON DELETE CASCADE,
  bbl                CHAR(10),
  trigger_type       TEXT NOT NULL,
  payload            JSONB NOT NULL,
  delivered_at       TIMESTAMPTZ,
  delivery_status    TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_alert_events_sub ON alert_events(subscription_id, created_at DESC);
```

### 3.4 Reports

```sql
CREATE TABLE generated_reports (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL REFERENCES users(id),
  agency_id          UUID NOT NULL REFERENCES agencies(id),
  bbl                CHAR(10) NOT NULL,
  report_type        TEXT NOT NULL,                   -- property | comp_set
  pdf_url            TEXT,
  generated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.5 ETL audit

```sql
CREATE TABLE sync_log (
  id                 BIGSERIAL PRIMARY KEY,
  dataset_id         TEXT NOT NULL,                   -- e.g., "64uk-42ks"
  dataset_name       TEXT NOT NULL,                   -- "PLUTO"
  started_at         TIMESTAMPTZ NOT NULL,
  completed_at       TIMESTAMPTZ,
  rows_fetched       INTEGER,
  rows_upserted      INTEGER,
  rows_deleted       INTEGER,
  status             TEXT NOT NULL,                   -- running | success | failed
  error_message      TEXT,
  high_watermark     TIMESTAMPTZ,                     -- max(updated_at) seen
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sync_log_dataset ON sync_log(dataset_id, started_at DESC);
```

---

## 4. Materialized views (built once, refreshed after each ETL run)

### 4.1 `mv_property_latest_sale`

Most recent ACRIS deed transfer per BBL.

```sql
CREATE MATERIALIZED VIEW mv_property_latest_sale AS
SELECT DISTINCT ON (l.bbl)
  l.bbl,
  m.document_id,
  m.doc_type,
  m.document_date AS sale_date,
  m.document_amt  AS sale_price
FROM acris_legals l
JOIN acris_master m ON m.document_id = l.document_id
WHERE m.doc_type IN ('DEED', 'DEEDO', 'BARGAIN AND SALE DEED')
ORDER BY l.bbl, m.document_date DESC;

CREATE UNIQUE INDEX ON mv_property_latest_sale(bbl);
```

### 4.2 `mv_property_violation_counts`

Open HPD + DOB violation counts per BBL.

```sql
CREATE MATERIALIZED VIEW mv_property_violation_counts AS
SELECT
  COALESCE(h.bbl, d.bbl) AS bbl,
  COALESCE(h.open_hpd, 0) AS open_hpd_violations,
  COALESCE(d.open_dob, 0) AS open_dob_violations
FROM (
  SELECT bbl, COUNT(*) AS open_hpd
  FROM hpd_violations WHERE current_status NOT ILIKE '%close%' GROUP BY bbl
) h FULL OUTER JOIN (
  SELECT bbl, COUNT(*) AS open_dob
  FROM dob_violations WHERE disposition_date IS NULL GROUP BY bbl
) d USING (bbl);

CREATE UNIQUE INDEX ON mv_property_violation_counts(bbl);
```

### 4.3 `mv_comps_recent` — last 24 months of arms-length sales

Used by the comps engine. Refresh after each ETL.

---

## 5. Migrations

Use **Prisma** (if Next.js Node backend) or **Alembic** (if FastAPI Python ETL).
Keep migrations versioned in `/db/migrations`. Never edit a committed migration — create a new one.

---

## 6. Estimated row counts (sanity check)

| Table | Approx rows |
|-------|-------------|
| properties | ~870,000 |
| acris_master | ~12 million |
| acris_legals | ~25 million |
| acris_parties | ~30 million |
| dof_sales | ~2 million |
| dob_permits | ~5 million |
| dob_violations | ~3 million |
| hpd_violations | ~6 million |
| complaints_311 (housing-filtered) | ~10 million |

Total: ~95 million rows, ~50 GB on disk with indexes.
**Budget for managed Postgres: 100 GB at minimum** (Supabase Pro, Neon Scale, or Railway).
