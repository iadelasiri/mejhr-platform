import { formatPriceValue } from "@/lib/format";
import type { CompanyPriceOut } from "@/types/prices";

interface Labels {
  tradeDate: string;
  notAvailable: string;
  unavailableMessage: string;
}

/**
 * Compact close/change/change_pct/trade_date/source ticker for the company
 * header — a trimmed view of the same data shown in full in PriceCard
 * (which stays unchanged, with volume/turnover/trades_count, lower on the
 * page). open/high/low/previous_close are never shown here: the type has
 * no fields for them.
 */
export default function PriceTicker({
  price,
  labels,
}: {
  price: CompanyPriceOut | null;
  labels: Labels;
}) {
  if (!price) {
    return <p className="text-xs text-gray-400 max-w-[180px] text-end">{labels.unavailableMessage}</p>;
  }

  const close = formatPriceValue(price.close, labels.notAvailable);
  const changeAmount = formatPriceValue(price.change_amount, labels.notAvailable);
  const changePct = formatPriceValue(price.change_pct, labels.notAvailable);

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
    <div className="text-end flex-shrink-0">
      <div dir="ltr" className="num text-2xl font-bold text-gray-900 dark:text-gray-100 leading-tight">
        {close.text}
      </div>
      <div dir="ltr" className={`num text-sm font-semibold ${changeColor}`}>
        {arrow}
        {changeAmount.text}
        {changePct.isAvailable && <span className="ms-1">({changePct.text}%)</span>}
      </div>
      <div className="text-xs text-gray-400 mt-0.5">
        {labels.tradeDate}: <span dir="ltr">{price.trade_date}</span>
      </div>
      {price.source && (
        <div className="text-xs text-gray-400 font-mono truncate max-w-[200px]">{price.source}</div>
      )}
    </div>
  );
}
