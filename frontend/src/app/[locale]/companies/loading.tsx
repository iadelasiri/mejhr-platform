export default function CompaniesListLoading() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6 animate-pulse">
      <div>
        <div className="h-7 w-40 bg-gray-200 dark:bg-gray-800 rounded" />
        <div className="h-4 w-72 bg-gray-200 dark:bg-gray-800 rounded mt-2" />
      </div>
      <div className="h-10 w-full bg-gray-200 dark:bg-gray-800 rounded-lg" />
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-12 border-b border-gray-100 dark:border-gray-800 last:border-0 bg-gray-50 dark:bg-gray-900/50"
          />
        ))}
      </div>
    </div>
  );
}
