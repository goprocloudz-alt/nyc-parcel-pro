// Shared TypeScript types for NYC Parcel Pro.
// Richer types (Prisma-generated models, Pydantic-derived interfaces) are added
// here as the schema stabilises. For now: the primitives every package needs.

// SCHEMA.md §1: borough display codes
export type Borough = "MN" | "BX" | "BK" | "QN" | "SI";

// SCHEMA.md §1: zero-padded 10-char string B(1)+Block(5)+Lot(4).
// Branded type prevents accidental numeric coercion (CLAUDE.md rule 8).
export type Bbl = string & { readonly __brand: "Bbl" };

export function toBbl(raw: string): Bbl {
  if (!/^\d{10}$/.test(raw)) {
    throw new Error(`Invalid BBL: "${raw}" — must be exactly 10 digits`);
  }
  return raw as Bbl;
}

// Socrata dataset IDs (stable identifiers from CLAUDE.md cheat sheet).
// Names drift; IDs do not — always reference by ID.
export const DATASET_IDS = {
  PLUTO:               "64uk-42ks",
  PLUTO_CHANGE:        "qt5r-nqxp",
  ACRIS_MASTER:        "bnx9-e6tj",
  ACRIS_LEGALS:        "8h5j-fqxa",
  ACRIS_PARTIES:       "636b-3b5g",
  ACRIS_DOC_CODES:     "7isb-wh4c",
  DOB_PERMITS:         "ipu4-2q9a",
  DOB_JOBS:            "ic3t-wcy2",
  DOB_VIOLATIONS:      "3h2n-5cm9",
  HPD_VIOLATIONS:      "wvxf-dwi5",
  HPD_REGISTRATIONS:   "tesw-yqqr",
  HOUSING_LITIGATIONS: "59kj-ewme",
  COMPLAINTS_311:      "erm2-nwe9",
} as const;

export type DatasetId = (typeof DATASET_IDS)[keyof typeof DATASET_IDS];

// ETL sync status values (mirrors sync_log.status — SCHEMA.md §3.5)
export type SyncStatus = "running" | "success" | "failed";
