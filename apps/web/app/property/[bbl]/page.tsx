import { notFound } from "next/navigation";

// Next.js 15: params is a Promise — must be awaited before use.
interface Props {
  params: Promise<{ bbl: string }>;
}

// PROJECT.md stories #1 (search + pull profile) and #2 (ownership, sales, value)
export default async function PropertyPage({ params }: Props) {
  const { bbl } = await params;

  // SCHEMA.md §1: BBL is zero-padded CHAR(10) — always a string, never numeric.
  if (!/^\d{10}$/.test(bbl)) notFound();

  return (
    <main className="min-h-screen p-6">
      <h1 className="text-2xl font-bold">Property {bbl}</h1>

      {/* CLAUDE.md rule 5: last_synced_at must always be visible to the user */}
      <p className="mt-2 text-sm text-gray-500">
        Data freshness: <em>— loading —</em>
      </p>

      {/* TODO: fetch via GET /api/v1/properties/[bbl] — PROJECT.md story #1 */}

      {/* CLAUDE.md rule 6 + PROJECT.md §8: required disclaimer on every property page */}
      <footer className="mt-12 border-t pt-4 text-xs text-gray-400">
        Information is for due diligence purposes only. It is not a title
        report, legal advice, or licensed appraisal. Verify all data with
        primary sources before transacting.
        {" | "}
        Data: NYC Open Data
      </footer>
    </main>
  );
}
