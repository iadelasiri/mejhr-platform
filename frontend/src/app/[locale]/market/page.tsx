import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import { api } from "@/lib/api";
import IndexCard from "@/components/market/IndexCard";
import type { IndexPriceOut, IndexPricesListResponse } from "@/types/prices";

export const metadata: Metadata = { title: "Market Indices — Mejhr" };

// TASI and MT30 are the only indices with full OHLCV from the source (see
// PHASE_2D2_DISCOVERY.md) — shown first/prominently. All other indices
// render identically; high/low simply come back null for them.
const MAIN_INDEX_CODES = new Set(["TASI", "MT30"]);

async function fetchIndices(): Promise<{
  indices: IndexPriceOut[];
  total: number;
  error: string | null;
}> {
  try {
    const res = (await api.marketIndicesLatest({ per_page: 200 })) as IndexPricesListResponse;
    return { indices: res.data, total: res.total, error: null };
  } catch (err) {
    return { indices: [], total: 0, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export default async function MarketPage({ params }: { params: { locale: string } }) {
  const { locale } = params;
  const t = await getTranslations("market");
  const tCommon = await getTranslations("common");
  const notAvailable = tCommon("notAvailable");

  const { indices, total, error } = await fetchIndices();

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 p-8 text-center space-y-2">
          <h2 className="font-semibold text-red-700 dark:text-red-300">{t("loadError")}</h2>
          <p className="text-sm text-red-600 dark:text-red-400">{t("loadErrorDesc")}</p>
          <p className="text-xs text-red-400 dark:text-red-500 font-mono mt-2">{error}</p>
        </div>
      </div>
    );
  }

  const labels = {
    open: t("columns.open"),
    high: t("columns.high"),
    low: t("columns.low"),
    volume: t("columns.volume"),
    turnover: t("columns.turnover"),
    tradesCount: t("columns.tradesCount"),
    tradeDate: t("columns.tradeDate"),
    source: t("columns.source"),
    notAvailable,
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      {indices.length === 0 ? (
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 p-12 text-center space-y-1">
          <p className="text-gray-600 dark:text-gray-300 font-medium">{t("noData")}</p>
          <p className="text-sm text-gray-400">{t("noDataDesc")}</p>
        </div>
      ) : (
        <>
          <div dir="ltr" className="num text-xs text-gray-400">
            {t("resultsCount", { count: total })}
          </div>

          {(() => {
            const mainIndices = indices.filter((i) => MAIN_INDEX_CODES.has(i.index_code));
            const otherIndices = indices.filter((i) => !MAIN_INDEX_CODES.has(i.index_code));
            return (
              <>
                {mainIndices.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {mainIndices.map((idx) => (
                      <IndexCard key={idx.index_code} index={idx} locale={locale} labels={labels} />
                    ))}
                  </div>
                )}
                {otherIndices.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {otherIndices.map((idx) => (
                      <IndexCard key={idx.index_code} index={idx} locale={locale} labels={labels} />
                    ))}
                  </div>
                )}
              </>
            );
          })()}
        </>
      )}
    </div>
  );
}
