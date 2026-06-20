import FinancialRow from "@/components/financials/FinancialRow";
import { formatPriceValue } from "@/lib/format";
import type { IndexPriceOut } from "@/types/prices";

interface Labels {
  open: string;
  high: string;
  low: string;
  volume: string;
  turnover: string;
  tradesCount: string;
  tradeDate: string;
  source: string;
  notAvailable: string;
}

/**
 * One index's latest price. open/high/low are rendered for every index —
 * never hidden by index_code — and simply show "unavailable" when the API
 * returns null (sector indices), exactly as TASI/MT30 show real values.
 * No special-casing by code: the data itself decides what's shown.
 */
export default function IndexCard({
  index,
  locale,
  labels,
}: {
  index: IndexPriceOut;
  locale: string;
  labels: Labels;
}) {
  const name = locale === "ar" ? index.index_name_ar : index.index_name_en;

  const close = formatPriceValue(index.close, labels.notAvailable);
  const changeAmount = formatPriceValue(index.change_amount, labels.notAvailable);
  const changePct = formatPriceValue(index.change_pct, labels.notAvailable);
  const open = formatPriceValue(index.open, labels.notAvailable);
  const high = formatPriceValue(index.high, labels.notAvailable);
  const low = formatPriceValue(index.low, labels.notAvailable);

  const changeColor = !changeAmount.isAvailable
    ? "text-gray-400 dark:text-gray-600"
    : changeAmount.isNegative
      ? "text-rose-600 dark:text-rose-400"
      : changeAmount.text === "0.00"
        ? "text-gray-500 dark:text-gray-400"
        : "text-emerald-600 dark:text-emerald-400";

  const arrow =
    !changeAmount.isAvailable || changeAmount.text === "0.00"
      ? ""
      : changeAmount.isNegative
        ? "▼ "
        : "▲ ";

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 border-t-2 border-t-cyan-500 rounded-xl p-4">
      <div className="flex items-baseline gap-2">
        <span className="font-mono font-bold text-gray-900 dark:text-gray-100">{index.index_code}</span>
        <span className="text-xs text-gray-400 truncate">{name ?? labels.notAvailable}</span>
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-3 py-2">
        <div dir="ltr" className="num text-xl font-bold text-gray-900 dark:text-gray-100">
          {close.text}
        </div>
        <div dir="ltr" className={`num text-sm font-semibold ${changeColor}`}>
          {arrow}
          {changeAmount.text}
          {changePct.isAvailable && <span className="ms-1">({changePct.text}%)</span>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center py-2 border-y border-gray-100 dark:border-gray-800">
        {[
          { label: labels.open, v: open },
          { label: labels.high, v: high },
          { label: labels.low, v: low },
        ].map(({ label, v }) => (
          <div key={label}>
            <div className="text-xs text-gray-400">{label}</div>
            <div
              dir={v.isAvailable ? "ltr" : undefined}
              className={`num text-sm ${v.isAvailable ? "text-gray-700 dark:text-gray-300" : "text-gray-400 dark:text-gray-600"}`}
            >
              {v.text}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-1">
        <FinancialRow label={labels.volume} value={index.volume} locale={locale} notAvailableText={labels.notAvailable} />
        <FinancialRow label={labels.turnover} value={index.turnover} locale={locale} notAvailableText={labels.notAvailable} />
        <FinancialRow label={labels.tradesCount} value={index.trades_count} locale={locale} notAvailableText={labels.notAvailable} />
      </div>

      <div className="flex items-baseline justify-between gap-2 text-xs text-gray-400 mt-2">
        <span>
          {labels.tradeDate}: <span dir="ltr">{index.trade_date}</span>
        </span>
        {index.source && <span className="font-mono truncate max-w-[50%]">{index.source}</span>}
      </div>
    </div>
  );
}
