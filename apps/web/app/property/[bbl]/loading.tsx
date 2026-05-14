export default function PropertyLoading() {
  return (
    <main className="min-h-screen bg-gray-50 p-6 animate-pulse">
      {/* Hero skeleton */}
      <div className="mb-6">
        <div className="h-8 w-72 rounded bg-gray-200" />
        <div className="mt-2 h-4 w-48 rounded bg-gray-200" />
      </div>

      {/* Section grid skeleton */}
      <div className="grid gap-4 md:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-lg border border-gray-200 bg-white p-5">
            <div className="mb-4 h-3 w-32 rounded bg-gray-200" />
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              {[0, 1, 2, 3, 4, 5].map((j) => (
                <div key={j}>
                  <div className="h-2.5 w-20 rounded bg-gray-200" />
                  <div className="mt-1.5 h-4 w-full rounded bg-gray-100" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Freshness footer skeleton */}
      <div className="mt-6 h-3 w-64 rounded bg-gray-200" />
    </main>
  );
}
