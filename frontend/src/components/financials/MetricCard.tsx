import { formatFinancialValue, formatPriceValue } from "@/lib/format";

/**
 * One scannable key-metric tile (label + big value). Only ever renders a
 * value already present in the approved financials/price API response —
 * no derived ratios, no calculations beyond display formatting.
 */
export default function MetricCard({
  label,
  value,
  locale,
  notAvailableText,
  variant = "financial",
}: {
  label: string;
  value: string | null;
  locale: string;
  notAvailableText: string;
  /** "price" uses 2-decimal formatting (e.g. close); "financial" uses 0-decimal comma grouping. */
  variant?: "financial" | "price";
}) {
  const formatted =
    variant === "price"
      ? formatPriceValue(value, notAvailableText)
      : formatFinancialValue(value, locale, notAvailableText);

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-3">
      <div className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">{label}</div>
      <div
        dir={formatted.isAvailable ? "ltr" : undefined}
        className={`num text-lg font-bold mt-1 ${
          !formatted.isAvailable
            ? "text-gray-400 dark:text-gray-600 font-normal text-sm"
            : formatted.isNegative
              ? "text-rose-600 dark:text-rose-400"
              : "text-gray-900 dark:text-gray-100"
        }`}
      >
        {formatted.text}
      </div>
    </div>
  );
}
