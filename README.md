# NYC Parcel Pro

Real estate intelligence platform for licensed NYC brokers and agencies.
Data sourced from NYC Open Data (Socrata), refreshed twice per month (1st and 15th).

See `PROJECT.md`, `SCHEMA.md`, and `ETL.md` for full specifications.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 20+ |
| pnpm | 9+ |
| Python | 3.12+ |
| uv | latest |
| Docker + Compose | v2 |

---

## Quick start

```bash
# 1. Copy env template and fill in secrets
cp .env.example .env
#    NEXTAUTH_SECRET is required: openssl rand -base64 32

# 2. Start local infrastructure (Postgres with PostGIS + Redis)
#    On first run, docker-entrypoint-initdb.d applies db/migrations/0001_initial.sql
#    which creates extensions, the properties table, and sync_log.
docker compose up -d

# 3. Install web app dependencies and apply Prisma migrations (agencies, users)
cd apps/web
pnpm install          # also generates pnpm-lock.yaml on first run
pnpm prisma migrate dev --name init
pnpm dev              # http://localhost:3000

# 4. (Optional) Run the ETL against the local DB
cd ../etl
uv sync
uv run python -m etl.run --dataset=64uk-42ks --dry-run
```

---

## Workspace layout

| Path | Contents |
|------|----------|
| `apps/web` | Next.js 15 app — TypeScript, Tailwind, shadcn/ui, Prisma |
| `apps/etl` | Python 3.12 ETL worker — httpx, psycopg, Pydantic |
| `packages/shared-types` | Shared TypeScript types (Borough, BBL, dataset IDs) |
| `db/migrations` | Raw SQL migrations for NYC-data tables (PostGIS, CITEXT) |

---

## Common commands

```bash
# Web
pnpm typecheck          # from apps/web or repo root
pnpm lint
pnpm test
pnpm prisma studio      # browse DB at http://localhost:5555

# ETL
uv run python -m etl.run --all
uv run pytest
uv run mypy etl/
uv run ruff check etl/

# Infrastructure
docker compose up -d
docker compose logs -f postgres
docker compose down -v   # destroys postgres_data volume — use with caution
```

---

## Data attribution

Data sourced from [NYC Open Data](https://opendata.cityofnewyork.us/) under the
NYC Open Data Terms of Use. Attribution required in application footer.
