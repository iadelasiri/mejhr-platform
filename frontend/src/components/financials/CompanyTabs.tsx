/**
 * Same-page anchor navigation. Plain <a href="#id"> links — no client JS,
 * no active-section tracking (out of scope for now). Only tabs for
 * sections that actually exist and show real data — no Ratios/Dividends/
 * Peers/Insights tabs, disabled or otherwise, to avoid implying data that
 * isn't there.
 */
export default function CompanyTabs({
  tabs,
}: {
  tabs: { id: string; label: string }[];
}) {
  return (
    <nav
      aria-label="Company sections"
      className="flex gap-1 overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-1.5"
    >
      {tabs.map((tab) => (
        <a
          key={tab.id}
          href={`#${tab.id}`}
          className="flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
        >
          {tab.label}
        </a>
      ))}
    </nav>
  );
}
