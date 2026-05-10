# NYC Parcel Pro — ETL Pipeline

**Goal:** Pull every relevant NYC Open Data dataset on the **1st and 15th of every month at 02:00 ET**, upsert into Postgres, and refresh materialized views.

---

## 1. Source: NYC Open Data via Socrata SODA API

**Base URL pattern:**
```
https://data.cityofnewyork.us/resource/{dataset-id}.json
```

**App token:** Register one free token at
`https://data.cityofnewyork.us/profile/edit/developer_settings`
Pass it on every request via the `X-App-Token` header. Without a token, requests are heavily throttled.

**Rate limits (with token):** ~10 requests/sec sustained. Plan for parallelism but cap concurrency at 5–8.

**Pagination:** Default page size is 1,000 rows. Max is 50,000. Use `$limit=50000` + `$order=:id` + `$where=:id > '{last_id}'` for keyset pagination (faster than `$offset`).

**Incremental sync:** Filter on `:updated_at`:
```
$where=:updated_at > '2026-04-15T00:00:00.000'
```
Use the high-watermark stored in `sync_log.high_watermark` for the dataset.

---

## 2. Datasets to ingest

| Dataset | Socrata ID | Sync mode | Approx volume per sync |
|---------|-----------|-----------|------------------------|
| PLUTO | `64uk-42ks` | full replace (versioned) | 870k rows once / quarter |
| PLUTO Change File | `qt5r-nqxp` | full replace | small |
| ACRIS Real Property Master | `bnx9-e6tj` | incremental on `:updated_at` | ~30–80k rows / 15 days |
| ACRIS Real Property Legals | `8h5j-fqxa` | incremental | ~80–150k |
| ACRIS Real Property Parties | `636b-3b5g` | incremental | ~100–200k |
| ACRIS Document Codes (lookup) | `7isb-wh4c` | full replace | ~150 rows |
| DOF Rolling Sales | varies by year | full replace per FY | ~80k rows |
| DOB Permits Issuance | `ipu4-2q9a` | incremental | ~30k / 15 days |
| DOB Job Applications | `ic3t-wcy2` | incremental | ~10k / 15 days |
| DOB Violations | `3h2n-5cm9` | incremental | ~20k / 15 days |
| HPD Violations | `wvxf-dwi5` | incremental | ~40k / 15 days |
| HPD Registrations | `tesw-yqqr` | full replace | ~180k |
| Housing Litigations | `59kj-ewme` | incremental | ~5k / 15 days |
| 311 Service Requests (housing-filtered) | `erm2-nwe9` | incremental + filter | ~50k / 15 days |
| FDNY Incidents | TBD | incremental | ~10k / 15 days |

For 311, filter at fetch time:
```
$where=agency='HPD' OR agency='DOB' OR complaint_type ILIKE '%housing%'
```

---

## 3. ETL architecture

```
┌────────────────────────────────────────────────────────┐
│  Replit Scheduled Deployment (cron: 0 2 1,15 * *)      │
│                                                         │
│  ┌──────────────────────────────────────────────┐      │
│  │  Python (FastAPI worker container)            │      │
│  │   ├─ fetcher.py     (Socrata → JSONL stream) │      │
│  │   ├─ transformer.py (BBL normalize, types)   │      │
│  │   ├─ loader.py      (UPSERT to Postgres)     │      │
│  │   ├─ refresher.py   (REFRESH MV CONCURRENTLY)│      │
│  │   └─ notifier.py    (Slack + email summary)  │      │
│  └──────────────────────────────────────────────┘      │
│                                                         │
│  Persists to → Postgres (same DB as web app)           │
└────────────────────────────────────────────────────────┘
```

Recommended language: **Python 3.12** with `httpx` (async HTTP), `psycopg[binary,pool]` (Postgres), `pydantic` (typing), and `tenacity` (retries).

Alternative: piggy-back on **NYCDB** (`github.com/nycdb/nycdb`) which already does most of this. Run its loaders in a Docker container and only maintain delta logic on top.

---

## 4. Pipeline contract

For every dataset, the pipeline must:

1. **Open a `sync_log` row** with `status='running'`, `started_at=now()`.
2. **Fetch** rows newer than the last successful high-watermark, in pages of 50k, with retries (exponential backoff, max 5 attempts).
3. **Stream to NDJSON on disk** (so a crash doesn't lose progress).
4. **Transform** each row:
   - Build BBL: `LPAD(borough,1,'0') || LPAD(block,5,'0') || LPAD(lot,4,'0')`
   - Coerce empty strings to `NULL`
   - Parse dates as ISO 8601 in `America/New_York`
   - Trim whitespace from text fields
5. **Upsert** to Postgres in batches of 5,000 using `INSERT ... ON CONFLICT (pk) DO UPDATE`. Wrap in a transaction per batch.
6. **Update high-watermark** to `MAX(:updated_at)` seen in this run.
7. **Close `sync_log` row** with `status='success'`, `completed_at`, `rows_*`, `high_watermark`.
8. **On any failure:** set `status='failed'`, `error_message`, send alert.

After ALL datasets complete (or partial success), run:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_property_latest_sale;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_property_violation_counts;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_comps_recent;
```

Then post a Slack/email summary:
```
NYC Parcel Pro ETL — 2026-05-15 02:47 ET
✓ PLUTO              (no new version)
✓ ACRIS Master       42,118 rows upserted
✓ ACRIS Legals       91,304 rows upserted
✓ DOB Permits        28,640 rows upserted
✗ HPD Violations     FAILED — Socrata 503 after 5 retries
✓ 311                51,221 rows upserted
Total runtime: 47m 12s
```

---

## 5. Handling PLUTO version changes

PLUTO is released versioned (e.g., `25v4`). When DCP publishes a new version:

1. Detect via metadata endpoint: `GET https://data.cityofnewyork.us/api/views/64uk-42ks.json` — check `dataUpdatedAt`.
2. If newer than our stored version:
   - Stage new data into `properties_staging` (same schema)
   - Diff against `properties` to identify added/removed/changed BBLs
   - Swap in a transaction:
     ```sql
     BEGIN;
     ALTER TABLE properties RENAME TO properties_old;
     ALTER TABLE properties_staging RENAME TO properties;
     ALTER TABLE properties_old RENAME TO properties_staging;
     TRUNCATE properties_staging;
     COMMIT;
     ```
   - Update `pluto_version` field on all rows
   - Log diff counts to `sync_log`

---

## 6. Geospatial handling (MapPLUTO)

MapPLUTO geometry is published per-borough as zipped shapefiles, not via Socrata JSON. Pipeline:

1. Download from DCP open-data S3 mirror (URLs change per release; scrape from the PLUTO page).
2. `ogr2ogr -f PostgreSQL "PG:..." MapPLUTO.shp -nln properties_geom -overwrite -t_srs EPSG:4326`
3. `UPDATE properties SET geom = pg.geom FROM properties_geom pg WHERE properties.bbl = pg.bbl;`

Run only when PLUTO version changes (every ~3 months), not every sync.

---

## 7. Address normalization

NYC addresses are inconsistent across datasets. Use **Geosupport** (free, runs locally as a Docker container) or **Geoclient API** to normalize.

For each user-typed address:
1. Call Geosupport `1B` function with the address
2. Receive: house number, street, BBL, BIN, zip, lat/lng
3. Cache resolved addresses in a `geocode_cache` table for 90 days

Geosupport Docker: `nycplanning/docker-geosupport`

---

## 8. Scheduling

**Replit Scheduled Deployment:**
- Cron: `0 2 1,15 * *` (1st and 15th, 02:00 ET — set timezone to `America/New_York`)
- Timeout: 4 hours
- Container: `python:3.12-slim`
- Env: `SOCRATA_APP_TOKEN`, `DATABASE_URL`, `SLACK_WEBHOOK_URL`, `SENDGRID_API_KEY`

**Failure recovery:**
- If a run fails partway, the next manual or scheduled run picks up from the high-watermark of the *last successful* sync per dataset (datasets are independent).
- An admin endpoint `POST /admin/etl/run?datasets=hpd_violations` triggers a single-dataset re-run.

---

## 9. Local development

```bash
# Spin up Postgres + Geosupport
docker compose up -d

# Seed Manhattan-only PLUTO subset
python -m etl.seed --borough=MN --limit=10000

# Run a single-dataset sync against the local DB
python -m etl.run --dataset=acris_master --since=2026-04-01

# Run the full pipeline (matches prod)
python -m etl.run --all
```

`docker-compose.yml` should provide:
- `postgres` (with PostGIS image)
- `geosupport` (NYC address normalizer)
- `redis` (for app cache)

---

## 10. Monitoring

**Admin dashboard page** (`/admin/etl`) shows:

- Last 30 days of sync_log entries per dataset, with status icons
- Current high-watermark per dataset
- Row count delta per run (sparkline)
- "Run now" button for each dataset (admin-only)
- Slack-style notification log

**Alerts:**
- Slack webhook on any failed dataset
- PagerDuty / email if pipeline does not complete within 4 hours of scheduled start

---

## 11. Cost expectations

| Item | Estimated cost |
|------|----------------|
| Socrata API | $0 (free with token) |
| Geosupport (self-hosted) | ~$5/mo VPS or free on Replit |
| Postgres (100 GB managed) | $25–80/mo (Supabase Pro / Neon Scale) |
| Replit scheduled deployments | $0–20/mo |
| Egress (Mapbox tiles, etc.) | $0–50/mo until pilot scale |
| **Total ETL infra (MVP)** | **~$40–100/mo** |
