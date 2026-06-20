import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import { fetchAllCompanies } from "@/lib/fetchAllCompanies";
import ComingLaterStrip from "@/components/financials/ComingLaterStrip";
import ScreenerClient from "./ScreenerClient";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("screener");
  return { title: t("title") };
}

/**
 * Tadawul-only screener. Built entirely on the existing bulk
 * GET /companies/ endpoint (via fetchAllCompanies) — same data source as
 * /companies, no new backend calls. No ratios, valuation, or per-company
 * price calls — see ComingLaterStrip and the accompanying report for the
 * documented gaps (bulk pricing endpoint, financial-data/quality flags).
 */
export default async function ScreenerPage({ params }: { params: { locale: string } }) {
  const t = await getTranslations("screener");
  const tCommon = await getTranslations("common");
  const { companies, error } = await fetchAllCompanies();

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t("subtitle")}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
            <span className="status-dot status-dot-green" />
            {t("provenance")}
          </span>
          <span dir="ltr" className="num text-xs text-gray-400">
            {t("countLabel", { count: companies.length })}
          </span>
        </div>
      </div>

      <ScreenerClient
        companies={companies}
        error={error}
        locale={params.locale}
        labels={{
          searchPlaceholder: t("searchPlaceholder"),
          sectorLabel: t("filters.sector"),
          allSectors: t("filters.allSectors"),
          mappingStatusLabel: t("filters.mappingStatus"),
          allStatuses: t("filters.allStatuses"),
          resetLabel: t("filters.reset"),
          tabAll: t("tabs.all"),
          tabMapped: t("tabs.mapped"),
          tabUnmapped: t("tabs.unmapped"),
          colSymbol: t("columns.symbol"),
          colNameAr: t("columns.nameAr"),
          colNameEn: t("columns.nameEn"),
          colMarket: t("columns.market"),
          colSector: t("columns.sector"),
          colMappingStatus: t("columns.mappingStatus"),
          noResults: t("noResults"),
          noResultsDesc: t("noResultsDesc"),
          loadError: t("loadError"),
          loadErrorDesc: t("loadErrorDesc"),
          notAvailable: tCommon("notAvailable"),
        }}
      />

      <ComingLaterStrip
        title={t("comingLater.title")}
        items={[
          t("comingLater.ratios"),
          t("comingLater.roic"),
          t("comingLater.evic"),
          t("comingLater.valuation"),
          t("comingLater.dividends"),
          t("comingLater.peers"),
        ]}
      />
    </div>
  );
}
