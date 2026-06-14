import { getTranslations } from "next-intl/server";
import { useTranslations } from "next-intl";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("screener");
  return { title: t("title") };
}

export default function ScreenerPage() {
  const t = useTranslations("screener");
  const tc = useTranslations("common");

  return (
    <div className="max-w-screen-2xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("subtitle")}</p>
      </div>

      {/* Filter bar placeholder */}
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <div className="flex flex-wrap gap-3">
          {["Market", "Sector", "Min Market Cap", "Min ROIC", "Max P/E"].map((f) => (
            <div
              key={f}
              className="h-9 w-36 bg-gray-200 dark:bg-gray-700 rounded-lg animate-pulse"
            />
          ))}
          <button className="h-9 px-4 bg-mejhr-600 text-white rounded-lg text-sm font-medium opacity-50 cursor-not-allowed">
            Apply
          </button>
        </div>
      </div>

      {/* Empty state */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl">
        {/* Table header */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-800 text-gray-500 dark:text-gray-400">
                {[
                  t("columns.symbol"),
                  t("columns.company"),
                  t("columns.market"),
                  t("columns.sector"),
                  t("columns.price"),
                  t("columns.change"),
                  t("columns.marketCap"),
                  t("columns.revenue"),
                  t("columns.netIncome"),
                  t("columns.roic"),
                  t("columns.evic"),
                  t("columns.pe"),
                  t("columns.dataQuality"),
                ].map((col) => (
                  <th
                    key={col}
                    className="px-4 py-3 text-left font-medium whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={13} className="px-4 py-16 text-center text-gray-400">
                  <div className="space-y-2">
                    <div className="text-base font-medium text-gray-500 dark:text-gray-400">
                      {t("noData")}
                    </div>
                    <div className="text-sm text-gray-400 dark:text-gray-500 max-w-md mx-auto">
                      {t("noDataDesc")}
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
