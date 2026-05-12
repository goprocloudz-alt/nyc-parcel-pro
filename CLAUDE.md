# CLAUDE.md

This file is read by Claude Code at the start of every session. Keep it concise and current. When something here goes stale, update it.

---

## Project: NYC Parcel Pro

A B2B real estate intelligence platform for licensed NYC brokers and agencies. Pulls authoritative parcel and real estate data for the five boroughs from NYC Open Data, refreshed twice per month (1st and 15th).

**Read first:** `PROJECT.md`, `SCHEMA.md`, `ETL.md` for full specs. Don't restate them here — refer to them.

---

## Stack

- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui
- **Backend:** Next.js API routes for the web app; Python 3.12 + FastAPI as a separate service for the ETL worker
- **Database:** PostgreSQL 16 + PostGIS 3.4 (single shared DB for app + ETL data)
- **ORM:** Prisma (web app); raw `psycopg` (ETL worker)
- **Mapping:** Mapbox GL JS with MapPLUTO vector tiles
- **Auth:** NextAuth (email/password + Google OAuth)
- **Cache:** Redis (Upstash in prod, local container in dev)
- **PDF:** Puppeteer in a worker container
- **Deploy:** Replit (MVP), migrating to Vercel + Supabase if we outgrow

---

## Repo layout

```
/
├── apps/
│   ├── web/                # Next.js app
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── prisma/
│   └── etl/                # Python ETL worker
│       ├── etl/
│       │   ├── fetcher.py
│       │   ├── transformer.py
│       │   ├── loader.py
│       │   └── run.py
│       └── pyproject.toml
├── packages/
│   └── shared-types/       # TS types generated from Prisma + Pydantic models
├── db/
│   └── migrations/
├── docker-compose.yml      # Postgres + Geosupport + Redis for local dev
├── PROJECT.md
├── SCHEMA.md
├── ETL.md
└── CLAUDE.md               # this file
```

---

## Common commands

```bash
# Web app
cd apps/web
pnpm install
pnpm dev                    # http://localhost:3000
pnpm test                   # vitest
pnpm typecheck
pnpm lint
pnpm prisma migrate dev     # apply migrations
pnpm prisma studio          # browse DB

# ETL worker
cd apps/etl
uv sync
uv run python -m etl.run --dataset=pluto --limit=10000 --dry-run  # dev: fetch+transform, no DB
uv run python -m etl.run --dataset=pluto --limit=10000             # dev: first 10k rows → Supabase
uv run python -m etl.run --dataset=pluto                           # full PLUTO run (~870k rows)
uv run python -m etl.run --all
uv run pytest

# Local infra
docker compose up -d        # postgres, geosupport, redis
docker compose logs -f etl
```

---

## Coding conventions

- **TypeScript:** strict mode on. No `any` without a `// eslint-disable-next-line` and a comment explaining why.
- **Python:** type hints required. `mypy --strict` must pass on the `etl/` package.
- **Imports:** absolute paths from package root (`@/lib/...` in web, `etl.fetcher` in Python). No `../../..` chains.
- **Error handling:** never swallow exceptions silently. Log with structured fields (`logger.error("sync_failed", dataset=name, error=str(e))`).
- **Database:** all writes go through Prisma (web) or `psycopg` parameterized queries (ETL). No string-concatenated SQL. Ever.
- **API:** REST under `/api/v1/...`. Validate request bodies with Zod (web) or Pydantic (ETL admin endpoints).
- **Tests:** every new API route ships with at least a happy-path and one error-case test. ETL transformers must have unit tests with sample Socrata payloads checked into `apps/etl/tests/fixtures/`.
- **Commits:** conventional commits (`feat:`, `fix:`, `chore:`, `docs:`). One logical change per commit.

---

## NYC datasets cheat sheet

Always reference Socrata datasets by ID (they're stable; names drift):

| Dataset | ID | Notes |
|---------|----|----|
| PLUTO | `64uk-42ks` | Master parcel record. Quarterly major releases, current = 25v4. |
| PLUTO Change | `qt5r-nqxp` | Companion to PLUTO, tracks DCP's manual edits. |
| ACRIS Master | `bnx9-e6tj` | Document headers (deeds, mortgages). |
| ACRIS Legals | `8h5j-fqxa` | Links documents to BBLs. |
| ACRIS Parties | `636b-3b5g` | Buyers, sellers, lenders. |
| ACRIS Doc Codes | `7isb-wh4c` | Lookup table for doc_type values. |
| DOB Permits | `ipu4-2q9a` | Issued permits. |
| DOB Jobs | `ic3t-wcy2` | Job application filings. |
| DOB Violations | `3h2n-5cm9` | Active and historical violations. |
| HPD Violations | `wvxf-dwi5` | Class A/B/C/I housing violations. |
| HPD Registrations | `tesw-yqqr` | Required for buildings with 3+ units. |
| Housing Litigations | `59kj-ewme` | HPD vs owner court cases. |
| 311 Service Requests | `erm2-nwe9` | Filter to housing/building. |

**BBL format:** zero-padded 10-char string. Borough(1) + Block(5) + Lot(4). Example: `1000160001` = Manhattan, block 16, lot 1.

**Borough codes:**
| Number (PLUTO/ACRIS) | Letter (display) |
|------|-------|
| 1 | MN — Manhattan |
| 2 | BX — Bronx |
| 3 | BK — Brooklyn |
| 4 | QN — Queens |
| 5 | SI — Staten Island |

---

## Critical rules — DO NOT VIOLATE

1. **Never** commit secrets. `.env*` is gitignored. Use Replit Secrets / Doppler for prod.
2. **Never** edit a committed migration. Create a new one.
3. **Never** drop or truncate tables in app code paths. Only the ETL replace logic touches NYC-data tables, and only via staging-table swap.
4. **Never** call third-party APIs from a request hot path without caching. Geocoding, Socrata, Mapbox tiles — all cached.
5. **Never** display NYC data without its `last_synced_at` timestamp visible to the user.
6. **Always** include the disclaimer on the property detail page footer: *"Information is for due diligence purposes only. It is not a title report, legal advice, or licensed appraisal."*
7. **Always** scope queries by `agency_id` for any app-table read. Multi-tenant isolation is non-negotiable. Add a row-level security policy if it helps.
8. **Always** quote BBLs as strings in SQL/Prisma. Numeric coercion drops leading zeros.

---

## Performance targets

- Property detail page: <2s p95 (cold), <500ms p95 (cached)
- Search autocomplete: <300ms p95
- Comps query (1-mile radius, 24mo): <1s p95
- ETL full run: <90 minutes
- Map tile render: <200ms p95 (CDN)

---

## Known gotchas

- **PLUTO `:updated_at` is unreliable** for incremental sync. Use full-replace via staging table when DCP publishes a new version. Detect via the dataset metadata endpoint.
- **ACRIS `document_id` is sometimes reused** across record types. Always join on `(document_id, record_type)`.
- **311 `unique_key` is a string in some old rows** — coerce to BIGINT carefully, log and skip on failure.
- **Marble Hill and Rikers Island** are billing-borough quirks. Marble Hill is legally Manhattan but serviced by the Bronx; Rikers is legally Bronx, serviced by Queens. PLUTO uses legal borough.
- **Condo lots** are summarized to one record per condo complex by DCP. Don't try to split them back out.
- **Empty strings vs nulls** in Socrata responses: always coerce `""` to `NULL` in the transformer.
- **Mapbox vector tile size limit** (500 KB). Don't put all 870k MapPLUTO geometries in one tile — let Mapbox tile them server-side or use a hosted tileset.
- Build was scaffolded on macOS 12 — Docker is unavailable, so production DB is Supabase Postgres. Schema migrations applied via Supabase SQL Editor, NOT prisma migrate.
- .env lives only at repo root; symlinked into apps/web/ and apps/etl/ with `ln -s ../../.env .env`. Symlinks are gitignored.
- apps/etl/pyproject.toml requires [build-system] with hatchling and [tool.hatch.build.targets.wheel] packages = ["etl"] — the project name doesn't match the package dir name.
- psycopg 3 requires `async with conn.cursor() as cur:` before calling executemany.
- Supabase reserves auth.users; our public.users coexists fine but expect minor friction with Supabase Auth if we use it later.
- The .env symlinks in apps/web/ and apps/etl/ are NOT in git (they're machine-specific). After any clone, recreate them:
    cd apps/web && ln -s ../../.env .env
    cd apps/etl && ln -s ../../.env .env

---

## When asked to do X — defaults

- "Add a new dataset" → New table in `db/migrations`, new fetcher in `apps/etl/etl/datasets/`, new dashboard tile in `/admin/etl`.
- "Build a feature" → Plan mode first. Write the user-visible behavior in terms of the user stories in `PROJECT.md`. Cite which story.
- "Fix a bug" → Reproduce with a failing test before changing code.
- "Refactor" → Show the plan before touching files. Refactors >5 files require explicit approval in plan mode.
- "Deploy" → Don't. Show the deploy diff and wait for approval.

---

## What "done" looks like for any task

- [ ] Code compiles, typecheck passes, lint passes
- [ ] Tests pass (and new ones added for new behavior)
- [ ] If schema changed: migration created and applied locally
- [ ] If a Socrata field is referenced: cited by ID, not name
- [ ] User-visible changes have the data freshness badge
- [ ] No secrets, no `console.log` debug, no `print()` left behind
- [ ] Commit message follows conventional commits

---

## Claude Code interaction style

- Default to **plan mode** for anything touching more than 2 files.
- Cite which `PROJECT.md` user story or `SCHEMA.md` table you're working against.
- Surface trade-offs before picking. Don't silently choose between "fast but coupled" and "clean but slow."
- If a request conflicts with a rule above, stop and ask.
