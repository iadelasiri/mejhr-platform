import { getTranslations } from "next-intl/server";
import { api } from "@/lib/api";
import { formatPriceValue } from "@/lib/format";
import type { IndexPriceOut, IndexPricesListResponse } from "@/types/prices";

// Only TASI and MT30 — the two indices with full official OHLCV. A slim,
// persistent summary strip (design direction from the old Mejhr UI's
// "market strip"), built entirely from the existing approved
// GET /market/indices/latest endpoint. No new data, no calculation.
const STRIP_CODES = new Set(["TASI", "MT30"]);

async function fetchStripIndices(): Promise<IndexPriceOut[]> {
  try {
    const res = (await api.marketIndicesLatest({ per_page: 200 })) as IndexPricesListResponse;
    return res.data.filter((i) => STRIP_CODES.has(i.index_code));
  } catch {
    return [];
  }
}

export default async function MarketStrip() {
  const t = await getTranslations("marketStrip");
  const tCommon = await getTranslations("common");
  const notAvailable = tCommon("notAvailable");
  const indices = await fetchStripIndices();

  return (
    <div className="sticky top-14 z-40 border-b border-gray-200 dark:border-gray-800 bg-gray-50/95 dark:bg-gray-900/90 backdrop-blur-sm">
      <div className="max-w-screen-2xl mx-auto px-4 h-9 flex items-center gap-5 overflow-x-auto text-xs">
        {indices.length === 0 ? (
          <span className="text-gray-400">{t("noData")}</span>
        ) : (
          indices.map((idx) => {
            const close = formatPriceValue(idx.close, notAvailable);
            const changeAmount = formatPriceValue(idx.change_amount, notAvailable);
            const changePct = formatPriceValue(idx.change_pct, notAvailable);
            const color = !changeAmount.isAvailable
              ? "text-gray-400 dark:text-gray-600"
              : changeAmount.isNegative
                ? "text-rose-600 dark:text-rose-400"
                : "text-emerald-600 dark:text-emerald-400";
            const arrow = !changeAmount.isAvailable ? "" : changeAmount.isNegative ? "▼" : "▲";

            return (
              <div key={idx.index_code} dir="ltr" className="flex items-baseline gap-1.5 flex-shrink-0">
                <span className="font-mono font-semibold text-gray-600 dark:text-gray-400">{idx.index_code}</span>
                <span className="num font-bold text-gray-900 dark:text-gray-100">{close.text}</span>
                <span className={`num font-semibold ${color}`}>
                  {arrow} {changeAmount.text}
                  {changePct.isAvailable ? ` (${changePct.text}%)` : ""}
                </span>
              </div>
            );
          })
        )}

        <div className="ms-auto flex items-center gap-1.5 flex-shrink-0">
          <span className="status-dot status-dot-green" />
          <span className="text-gray-500 dark:text-gray-400 whitespace-nowrap">{t("provenance")}</span>
        </div>
      </div>
    </div>
  );
}
