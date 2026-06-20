export default function CompanyFinancialsLoading() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6 animate-pulse">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <div className="h-7 w-24 bg-gray-200 dark:bg-gray-800 rounded" />
          <div className="h-5 w-56 bg-gray-200 dark:bg-gray-800 rounded" />
        </div>
        <div className="h-9 w-28 bg-gray-200 dark:bg-gray-800 rounded-lg" />
      </div>
      <div className="h-40 bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-64 bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl"
          />
        ))}
      </div>
      <div className="h-40 bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl" />
    </div>
  );
}
