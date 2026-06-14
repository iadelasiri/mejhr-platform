import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import Link from "next/link";

export async function generateMetadata({
  params,
}: {
  params: { symbol: string };
}): Promise<Metadata> {
  return { title: `${params.symbol.toUpperCase()} Statements — Mejhr` };
}

export default async function StatementsPage({
  params,
}: {
  params: { symbol: string; locale: string };
}) {
  const symbol = params.symbol.toUpperCase();

  const STATEMENT_TABS = [
    "Income Statement",
    "Balance Sheet",
    "Cash Flow",
    "XBRL Raw View",
    "Normalized View",
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href={`/company/${params.symbol}`}
          className="text-sm text-mejhr-600 dark:text-mejhr-400 hover:underline"
        >
          ← {symbol}
        </Link>
        <span className="text-gray-300 dark:text-gray-700">/</span>
        <h1 className="text-lg font-semibold text-gray-900 dark:text-white">Financial Statements</h1>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-2">
        {["Annual", "Quarterly"].map((t) => (
          <button
            key={t}
            className="px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 hover:border-mejhr-400 transition-colors"
          >
            {t}
          </button>
        ))}
        <select className="px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400">
          <option>Select Fiscal Year</option>
        </select>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-800">
        <div className="flex gap-0.5 overflow-x-auto">
          {STATEMENT_TABS.map((tab, i) => (
            <button
              key={tab}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                i === 0
                  ? "border-mejhr-500 text-mejhr-600 dark:text-mejhr-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Empty state */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-16 text-center space-y-2">
        <p className="font-medium text-gray-500 dark:text-gray-400">No financial statements available</p>
        <p className="text-sm text-gray-400 dark:text-gray-500">
          Run the XBRL pipeline in Phase 2 to discover, download, parse, and normalize statements for {symbol}.
        </p>
        <div className="text-xs text-gray-400 mt-4 space-y-1">
          <p>Pipeline steps required: xbrl_discovery → xbrl_download → xbrl_render → xbrl_parse → normalize</p>
          <p>No values are fabricated. Missing data is shown as empty.</p>
        </div>
      </div>
    </div>
  );
}
