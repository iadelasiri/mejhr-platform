import Link from "next/link";
import { QUICK_SAMPLE_SYMBOLS } from "@/types/financials";

/**
 * Visible quick links to the 6 sample symbols this MVP has been verified
 * against (2240, 2222, 2020, 4263, 2050, 1120). Pure navigation — no data
 * fetching, no calculations.
 */
export default function QuickSampleLinks({ locale, label }: { locale: string; label: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}:</span>
      {QUICK_SAMPLE_SYMBOLS.map((symbol) => (
        <Link
          key={symbol}
          href={`/${locale}/companies/${symbol}`}
          className="px-2.5 py-1 text-xs font-mono font-semibold rounded-lg border border-mejhr-200 dark:border-mejhr-800 text-mejhr-700 dark:text-mejhr-300 hover:bg-mejhr-50 dark:hover:bg-mejhr-950 transition-colors"
        >
          {symbol}
        </Link>
      ))}
    </div>
  );
}
