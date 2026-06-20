import SectionCard from "@/components/financials/SectionCard";
import FinancialRow from "@/components/financials/FinancialRow";
import { formatPriceValue } from "@/lib/format";
import type { CompanyPriceOut } from "@/types/prices";

interface Labels {
  title: string;
  close: string;
  changeAmount: string;
  changePct: string;
  volume: string;
  turnover: string;
  tradesCount: string;
  tradeDate: string;
  source: string;
  notAvailable: string;
  unavailableMessage: string;
}

/**
 * Latest company price — close/change/volume/turnover/trades_count only.
 * open/high/low/previous_close are never rendered here: the API does not
 * return them for this endpoint (see GET /companies/{symbol}/prices/latest),
 * and CompanyPriceOut has no fields for them — there is nothing to omit by
 * mistake.
 */
export default function PriceCard({
  price,
  locale,
  labels,
}: {
  price: CompanyPriceOut | null;
  locale: string;
  labels: Labels;
}) {
  if (!price) {
    return (
      <SectionCard title={labels.title} accent="price">
        <p className="text-sm text-gray-400 py-2">{labels.unavailableMessage}</p>
      </SectionCard>
    );
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

  const arrow = !changeAmount.isAvailable || changeAmount.text === "0.00"
    ? ""
    : changeAmount.isNegative
      ? "▼ "
      : "▲ ";

  return (
    <SectionCard title={labels.title} accent="price">
      <div className="flex flex-wrap items-baseline justify-between gap-3 py-1.5">
        <div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{labels.close}</div>
          <div dir="ltr" className="num text-2xl font-bold text-gray-900 dark:text-gray-100">
            {close.text}
          </div>
        </div>
        <div className="text-end">
          <div dir="ltr" className={`num text-sm font-semibold ${changeColor}`}>
            {arrow}{changeAmount.text}
            {changePct.isAvailable && <span className="ms-1">({changePct.text}%)</span>}
          </div>
          <div className="text-xs text-gray-400 mt-0.5">{labels.tradeDate}: {price.trade_date}</div>
        </div>
      </div>

      <div className="mt-1">
        <FinancialRow label={labels.volume} value={price.volume} locale={locale} notAvailableText={labels.notAvailable} />
        <FinancialRow label={labels.turnover} value={price.turnover} locale={locale} notAvailableText={labels.notAvailable} />
        <FinancialRow label={labels.tradesCount} value={price.trades_count} locale={locale} notAvailableText={labels.notAvailable} />
      </div>

      {price.source && (
        <p className="text-xs text-gray-400 mt-2 font-mono">{labels.source}: {price.source}</p>
      )}
    </SectionCard>
  );
}
