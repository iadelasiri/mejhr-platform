import { formatFinancialValue } from "@/lib/format";

/**
 * One labeled financial value row. Read-only display only — never computes
 * anything beyond locale-aware number formatting of the value already
 * returned by the API.
 */
export default function FinancialRow({
  label,
  value,
  locale,
  notAvailableText,
  unit,
}: {
  label: string;
  value: string | null;
  locale: string;
  notAvailableText: string;
  unit?: string;
}) {
  const formatted = formatFinancialValue(value, locale, notAvailableText);

  return (
    <div className="flex justify-between items-baseline py-2.5 border-b border-gray-100 dark:border-gray-800 last:border-0">
      <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
      <span
        // Force LTR only for the actual number — a plain "-" minus sign is a
        // weak bidi character that the browser can reposition to the wrong
        // side of the digits inside an RTL ancestor (e.g. "52,446,000-"
        // instead of "-52,446,000") unless explicitly isolated. The
        // "not available" fallback text is real Arabic/English prose and
        // must keep its natural direction, so dir is conditional.
        dir={formatted.isAvailable ? "ltr" : undefined}
        className={`num text-sm font-semibold ${
          !formatted.isAvailable
            ? "text-gray-400 dark:text-gray-600 font-normal"
            : formatted.isNegative
              ? "text-rose-600 dark:text-rose-400"
              : "text-gray-900 dark:text-gray-100"
        }`}
      >
        {formatted.text}
        {formatted.isAvailable && unit ? <span className="text-xs text-gray-400 ms-1">{unit}</span> : null}
      </span>
    </div>
  );
}
