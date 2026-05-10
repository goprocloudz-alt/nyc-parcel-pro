# NYC Parcel Pro — Project Specification

**Version:** 1.0
**Last updated:** 2026-05-10
**Owner:** [Your name]

---

## 1. Purpose

A real estate intelligence platform that gives licensed NYC brokers, agents, and agency administrators the most current and comprehensive parcel and real estate data available for any property in the five boroughs (Manhattan, Brooklyn, Queens, Bronx, Staten Island).

Data is sourced from authoritative NYC public APIs and refreshed twice per month (1st and 15th of every month, 02:00 ET).

---

## 2. Target users

### Primary
- **Licensed real estate brokers** — running comps, due diligence, and prospecting in NYC.
- **Real estate agents** — pulling property history before a showing or listing.
- **Agency administrators** — managing seats, branding, and shared watchlists.

### Secondary (future)
- Investment-sales analysts at small/mid-size firms.
- Title and legal due-diligence staff (read-only role).

### Out of scope
- Consumers (homebuyers/sellers) — this is a B2B tool.
- Properties outside the five boroughs.
- Replacement for title insurance, legal advice, or licensed appraisals.

---

## 3. User stories (MVP)

| # | As a... | I want to... | So that... |
|---|---------|--------------|------------|
| 1 | broker | search any NYC property by address, BBL, or owner | I can pull up a full profile in <2s |
| 2 | broker | see ownership, sales history, and assessed value on one page | I have negotiating context before a meeting |
| 3 | broker | view zoning, FAR, and remaining air rights | I can advise on development potential |
| 4 | broker | find sales comps within a configurable radius | I can price a listing or offer |
| 5 | broker | export a branded PDF property report | I can leave it with a client |
| 6 | broker | save a property to a watchlist | I get alerted when something changes |
| 7 | agent | get email/SMS alerts on new deeds, permits, or violations on watched properties | I am the first to know |
| 8 | admin | invite agents to my agency workspace | seats are managed centrally |
| 9 | admin | upload a logo for branded reports | reports look like ours, not Anthropic's |
| 10 | broker | see "data last synced" on every page | I know how stale anything is |

---

## 4. Feature scope by phase

### Phase 1 (MVP — first 4 weeks)
- Email/password auth with agency workspaces
- Property search (address, BBL, owner) with autocomplete
- Property detail page with PLUTO data + Mapbox map
- ACRIS sales/deed history
- DOB permits, HPD violations, 311 complaints
- Sync log + last-updated badges

### Phase 2 (weeks 5–8)
- Comps engine with radius + filters
- Branded PDF report generator
- Saved searches and watchlists
- ETL scheduled deployment running on the 1st and 15th

### Phase 3 (weeks 9–12)
- Email/SMS alerts on watched-property changes
- Multi-user agency workspaces with roles
- Rent-stabilization layer
- Eviction filings layer
- Admin dashboard with sync health

### Phase 4 (post-launch)
- Air rights / development potential calculator
- Map heatmaps (sales density, $/sqft, violations)
- API access for agencies on the top tier
- Mobile app wrapper (PWA → React Native if needed)

---

## 5. Non-goals (explicitly NOT building)

- A consumer-facing Zillow/StreetEasy clone.
- A CRM or transaction-management system.
- A mortgage origination or underwriting tool.
- Guaranteed real-time data — refresh is twice monthly. Brokers needing live ACRIS searches must still use the city's portal.
- Title-quality records — we are informational only.

---

## 6. Success metrics

| Metric | MVP target | 6-month target |
|--------|-----------|----------------|
| Time-to-property-detail | <2s p95 | <1s p95 |
| Agencies onboarded | 5 (pilot) | 50 |
| Active brokers (weekly) | 25 | 250 |
| Properties searched per active broker / week | 20 | 50 |
| ETL job success rate | 95% | 99% |
| Data freshness (max staleness for non-PLUTO datasets) | <16 days | <16 days |

---

## 7. Data freshness commitments (must be displayed in-app)

| Dataset | Source cadence | Our refresh | Max staleness shown |
|---------|----------------|-------------|---------------------|
| PLUTO | Quarterly (DCP) | 1st & 15th | Up to ~14 days behind DCP release |
| ACRIS | Daily | 1st & 15th | Up to 15 days |
| DOB permits/violations | Daily | 1st & 15th | Up to 15 days |
| HPD violations | Daily | 1st & 15th | Up to 15 days |
| 311 complaints | Near real-time | 1st & 15th | Up to 15 days |
| DOF rolling sales | Quarterly | 1st & 15th | Up to 15 days behind DOF |

Every property detail page must display the per-dataset `last_synced_at` timestamp.

---

## 8. Compliance & legal

- **Disclaimer (footer + property page):** "Information is for due diligence purposes only. It is not a title report, legal advice, or licensed appraisal. Verify all data with primary sources before transacting."
- **Data licensing:** All NYC Open Data is public domain / NYC Open Data terms — re-use permitted, attribution required in footer ("Data: NYC Open Data").
- **PII:** ACRIS contains owner names (public record). Do not enrich with non-public PII. Do not sell or transfer user-account data.
- **SOC 2 / SOC equivalent:** Not required for MVP. Revisit before enterprise sales.

---

## 9. Pricing (preliminary — not built into MVP)

| Tier | Price | Seats | Reports/mo | Watched properties | Alerts |
|------|-------|-------|------------|---------------------|--------|
| Solo | $49/mo | 1 | 25 | 50 | Email |
| Team | $149/mo | 5 | 200 | 500 | Email + SMS |
| Agency | $399/mo | 20 | Unlimited | Unlimited | Email + SMS + Webhooks |

MVP: free for all pilot users, no billing wired up.

---

## 10. Risks & open questions

- **PLUTO version drift.** PLUTO is released quarterly with versioned schema (currently 25v4). Need a migration story when DCP changes field names.
- **Address normalization.** NYC addresses are messy. Use Geosupport (free) or Geoclient API. Plan ~1 sprint for this.
- **Rate limits.** Socrata enforces rate limits without an app token. Register one early.
- **Storage.** Full NYCDB is ~50 GB. Plan for managed Postgres ($25–80/mo).
- **Map cost.** Mapbox free tier covers ~50k loads/mo. Watch the bill once we pass pilot.
- **PDF generation.** Puppeteer is heavy in serverless. Consider a small worker container if we hit cold-start issues.
