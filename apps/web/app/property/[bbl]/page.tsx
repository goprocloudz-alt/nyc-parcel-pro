import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";

// Next.js 15: params is a Promise — must be awaited before use.
interface Props {
  params: Promise<{ bbl: string }>;
}

// SCHEMA.md §2.1: $queryRaw returns snake_case column names. @@ignore on the
// Property model prevents prisma.property.findUnique(); we select every column
// except the unsupported `geom` PostGIS geometry field.
interface PropertyRow {
  bbl: string;
  borough: string;
  block: number;
  lot: number;
  cd: number | null;
  council_district: number | null;
  zip_code: string | null;
  address: string | null;
  owner_name: string | null;
  lot_area: number | null;
  bldg_area: number | null;
  com_area: number | null;
  res_area: number | null;
  office_area: number | null;
  retail_area: number | null;
  num_bldgs: number | null;
  num_floors: Prisma.Decimal | null;
  units_res: number | null;
  units_total: number | null;
  year_built: number | null;
  bldg_class: string | null;
  land_use: string | null;
  zone_dist1: string | null;
  zone_dist2: string | null;
  overlay1: string | null;
  overlay2: string | null;
  resid_far: Prisma.Decimal | null;
  comm_far: Prisma.Decimal | null;
  built_far: Prisma.Decimal | null;
  assess_land: Prisma.Decimal | null;
  assess_tot: Prisma.Decimal | null;
  exempt_tot: Prisma.Decimal | null;
  landmark: string | null;
  easements: number | null;
  owner_type: string | null;
  hist_dist: string | null;
  latitude: Prisma.Decimal | null;
  longitude: Prisma.Decimal | null;
  pluto_version: string;
  last_synced_at: Date;
}

// ETL confirmed: Socrata PLUTO 64uk-42ks ships "MN"/"BX"/"BK"/"QN"/"SI" in
// the `borough` field; the ETL passes it through unchanged. No numeric mapping.
const BOROUGH: Record<string, string> = {
  MN: "Manhattan",
  BX: "Bronx",
  BK: "Brooklyn",
  QN: "Queens",
  SI: "Staten Island",
};

const usdFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const sqftFmt = new Intl.NumberFormat("en-US");

function fmtUSD(v: Prisma.Decimal | null): string {
  return v == null ? "—" : usdFmt.format(v.toNumber());
}
function fmtSqft(v: number | null): string {
  return v == null ? "—" : `${sqftFmt.format(v)} sq ft`;
}
function fmtNum(v: number | Prisma.Decimal | null): string {
  return v == null ? "—" : String(v);
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm text-gray-900">{value}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-700">
        {title}
      </h2>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">{children}</dl>
    </div>
  );
}

// PROJECT.md stories #2 (ownership, assessed value) and #3 (zoning, FAR).
export default async function PropertyPage({ params }: Props) {
  const { bbl } = await params;

  // SCHEMA.md §1: BBL is zero-padded CHAR(10) — always a string, never numeric.
  if (!/^\d{10}$/.test(bbl)) notFound();

  // Prisma.sql uses parameterized binding — BBL is safely bound, no injection.
  // CLAUDE.md §DB: BBLs always quoted as strings in SQL; never coerced to numeric.
  const rows = await prisma.$queryRaw<PropertyRow[]>(
    Prisma.sql`
      SELECT bbl, borough, block, lot, cd, council_district, zip_code, address,
             owner_name, lot_area, bldg_area, com_area, res_area, office_area,
             retail_area, num_bldgs, num_floors, units_res, units_total,
             year_built, bldg_class, land_use, zone_dist1, zone_dist2,
             overlay1, overlay2, resid_far, comm_far, built_far,
             assess_land, assess_tot, exempt_tot, landmark, easements,
             owner_type, hist_dist, latitude, longitude,
             pluto_version, last_synced_at
      FROM   properties
      WHERE  bbl = ${bbl}
      LIMIT  1
    `
  );

  if (rows.length === 0) notFound();
  const p = rows[0];

  const boroughLabel = BOROUGH[p.borough] ?? p.borough;

  // All non-null fields for the collapsed "All PLUTO fields" panel.
  const allFields: Array<[string, string]> = (
    Object.entries(p) as Array<[string, unknown]>
  )
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]): [string, string] => [
      k,
      v instanceof Date ? v.toISOString() : String(v),
    ]);

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      {/* Hero — PROJECT.md story #1 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          {p.address ?? `BBL ${bbl}`}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {boroughLabel}
          {p.zip_code ? ` · ${p.zip_code}` : ""}
          {" · BBL "}
          <span className="font-mono">{bbl}</span>
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* PROJECT.md story #2: ownership and assessed value */}
        <Section title="Owner & Assessment">
          <Field label="Owner" value={p.owner_name ?? "—"} />
          <Field label="Owner type" value={p.owner_type ?? "—"} />
          <Field label="Assessed land" value={fmtUSD(p.assess_land)} />
          <Field label="Assessed total" value={fmtUSD(p.assess_tot)} />
          <Field label="Exempt total" value={fmtUSD(p.exempt_tot)} />
          <Field label="Landmark" value={p.landmark ?? "—"} />
          <Field label="Historic district" value={p.hist_dist ?? "—"} />
        </Section>

        {/* PROJECT.md story #2: building profile */}
        <Section title="Building">
          <Field label="Year built" value={fmtNum(p.year_built)} />
          <Field label="Bldg class" value={p.bldg_class ?? "—"} />
          <Field label="Land use" value={p.land_use ?? "—"} />
          <Field label="# buildings" value={fmtNum(p.num_bldgs)} />
          <Field label="# floors" value={fmtNum(p.num_floors)} />
          <Field label="Res. units" value={fmtNum(p.units_res)} />
          <Field label="Total units" value={fmtNum(p.units_total)} />
        </Section>

        <Section title="Areas">
          <Field label="Building area" value={fmtSqft(p.bldg_area)} />
          <Field label="Lot area" value={fmtSqft(p.lot_area)} />
          <Field label="Residential" value={fmtSqft(p.res_area)} />
          <Field label="Commercial" value={fmtSqft(p.com_area)} />
          <Field label="Office" value={fmtSqft(p.office_area)} />
          <Field label="Retail" value={fmtSqft(p.retail_area)} />
        </Section>

        {/* PROJECT.md story #3: zoning and FAR */}
        <Section title="Zoning">
          <Field label="Zone 1" value={p.zone_dist1 ?? "—"} />
          <Field label="Zone 2" value={p.zone_dist2 ?? "—"} />
          <Field label="Overlay 1" value={p.overlay1 ?? "—"} />
          <Field label="Overlay 2" value={p.overlay2 ?? "—"} />
          <Field label="Resid. FAR" value={fmtNum(p.resid_far)} />
          <Field label="Comm. FAR" value={fmtNum(p.comm_far)} />
          <Field label="Built FAR" value={fmtNum(p.built_far)} />
        </Section>
      </div>

      {/* Collapsed full field dump — no visual bloat when folded */}
      <details className="mt-6 rounded-lg border border-gray-200 bg-white">
        <summary className="cursor-pointer select-none px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50">
          All PLUTO fields
        </summary>
        <dl className="divide-y divide-gray-100 px-5 pb-4 font-mono text-xs">
          {allFields.map(([k, v]) => (
            <div key={k} className="flex gap-4 py-1.5">
              <dt className="w-44 shrink-0 text-gray-500">{k}</dt>
              <dd className="break-all text-gray-900">{v}</dd>
            </div>
          ))}
        </dl>
      </details>

      {/* CLAUDE.md rule 5: last_synced_at must always be visible */}
      <p className="mt-6 text-xs text-gray-400">
        Last synced:{" "}
        {p.last_synced_at.toLocaleDateString("en-US", {
          year: "numeric",
          month: "short",
          day: "numeric",
        })}{" "}
        · PLUTO version: {p.pluto_version} ·{" "}
        <abbr title="NYC Open Data dataset 64uk-42ks">Source: PLUTO 64uk-42ks</abbr>
      </p>

      {/* CLAUDE.md rule 6 + PROJECT.md §8: required disclaimer */}
      <footer className="mt-4 border-t pt-4 text-xs text-gray-400">
        Information is for due diligence purposes only. It is not a title
        report, legal advice, or licensed appraisal. Verify all data with
        primary sources before transacting.
        {" | "}
        Data: NYC Open Data
      </footer>
    </main>
  );
}
