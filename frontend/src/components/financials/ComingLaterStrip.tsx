/**
 * Explicitly inactive roadmap strip — names sections that are NOT
 * implemented (ratios, dividends, peers, etc.) with zero data and no
 * links, so the absence reads as "not built yet" rather than "broken" or
 * silently omitted. Never render a value here.
 */
export default function ComingLaterStrip({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-900/30 p-4">
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-2">
        {title}
      </p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span
            key={item}
            className="text-xs px-2.5 py-1 rounded-full border border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-600 bg-white dark:bg-gray-900"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
