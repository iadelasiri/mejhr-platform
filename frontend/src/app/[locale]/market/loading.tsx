export default function MarketLoading() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6 animate-pulse">
      <div>
        <div className="h-7 w-48 bg-gray-200 dark:bg-gray-800 rounded" />
        <div className="h-4 w-96 bg-gray-200 dark:bg-gray-800 rounded mt-2" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-48 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50" />
        ))}
      </div>
    </div>
  );
}
