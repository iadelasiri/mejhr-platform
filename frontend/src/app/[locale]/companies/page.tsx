import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import { fetchAllCompanies } from "@/lib/fetchAllCompanies";
import QuickSampleLinks from "@/components/companies/QuickSampleLinks";
import CompaniesListClient from "./CompaniesListClient";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("companiesList");
  return { title: t("title") };
}

export default async function CompaniesListPage({
  params,
}: {
  params: { locale: string };
}) {
  const t = await getTranslations("companiesList");
  const tCommon = await getTranslations("common");
  const { companies, error } = await fetchAllCompanies();

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      <QuickSampleLinks locale={params.locale} label={t("quickSamples")} />

      <CompaniesListClient
        companies={companies}
        error={error}
        locale={params.locale}
        labels={{
          searchPlaceholder: t("searchPlaceholder"),
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
    </div>
  );
}
