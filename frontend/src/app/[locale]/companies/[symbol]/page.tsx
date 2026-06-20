import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import SectionCard from "@/components/financials/SectionCard";
import FinancialRow from "@/components/financials/FinancialRow";
import DataQualityPanel from "@/components/financials/DataQualityPanel";
import CompanyHeaderCard from "@/components/financials/CompanyHeaderCard";
import PriceCard from "@/components/financials/PriceCard";
import QuickSampleLinks from "@/components/companies/QuickSampleLinks";
import { formatDateTime } from "@/lib/format";
import type { CompanyFinancialsResponse } from "@/types/financials";
import type { CompanyPriceOut, CompanyPriceResponse } from "@/types/prices";
import Link from "next/link";

// API_INTERNAL_URL (server-only) takes priority for this server-side fetch
// — see lib/api.ts for the full rationale (Docker container networking).
const API_URL =
  process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchFinancials(symbol: string): Promise<{
  result: CompanyFinancialsResponse | null;
  notFound: boolean;
  error: string | null;
}> {
  try {
    const res = await fetch(`${API_URL}/api/v1/companies/${symbol}/financials`, {
      next: { revalidate: 60 },
    });
    if (res.status === 404) {
      return { result: null, notFound: true, error: null };
    }
    if (!res.ok) {
      return { result: null, notFound: false, error: `HTTP ${res.status}` };
    }
    const result: CompanyFinancialsResponse = await res.json();
    if (!result.success || !result.data) {
      return { result, notFound: true, error: null };
    }
    return { result, notFound: false, error: null };
  } catch (err) {
    return { result: null, notFound: false, error: err instanceof Error ? err.message : "Network error" };
  }
}

/**
 * Latest price is supplementary — any failure (network, 404, no row yet)
 * degrades to null (rendered as a clean "unavailable" card) and never
 * blocks or errors the financials page itself.
 */
async function fetchLatestPrice(symbol: string): Promise<CompanyPriceOut | null> {
  try {
    const res = await fetch(`${API_URL}/api/v1/companies/${symbol}/prices/latest`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    const result: CompanyPriceResponse = await res.json();
    if (!result.success || !result.data) return null;
    return result.data;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: { symbol: string };
}): Promise<Metadata> {
  return { title: `${params.symbol.toUpperCase()} — Mejhr` };
}

export default async function CompanyFinancialsPage({
  params,
}: {
  params: { symbol: string; locale: string };
}) {
  const symbol = params.symbol.toUpperCase();
  const { locale } = params;
  const t = await getTranslations("financials");
  const tCommon = await getTranslations("common");
  const notAvailable = tCommon("notAvailable");

  const [{ result, notFound, error }, price] = await Promise.all([
    fetchFinancials(symbol),
    fetchLatestPrice(symbol),
  ]);

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center space-y-3">
        <h1 className="text-xl font-bold text-red-700 dark:text-red-300">{t("loadError")}</h1>
        <p className="text-sm text-red-500 font-mono">{error}</p>
        <Link href={`/${locale}/companies`} className="inline-block mt-2 text-sm text-mejhr-600 hover:underline">
          {t("backToList")}
        </Link>
      </div>
    );
  }

  if (notFound || !result?.data) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center space-y-3">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">{t("notFound")}</h1>
        <p className="text-gray-400 text-sm">Symbol: {symbol}</p>
        <p className="text-sm text-amber-600 dark:text-amber-400 max-w-md mx-auto">{t("notFoundDesc")}</p>
        {result?.meta?.message && (
          <p className="text-xs text-gray-400 max-w-md mx-auto font-mono">{result.meta.message}</p>
        )}
        <Link href={`/${locale}/companies`} className="inline-block mt-2 text-sm text-mejhr-600 hover:underline">
          {t("backToList")}
        </Link>
        <div className="pt-4">
          <QuickSampleLinks locale={locale} label={t("backToList")} />
        </div>
      </div>
    );
  }

  const data = result.data;
  const { company, filing, balance_sheet, income_statement, cash_flow, data_quality, metadata } = data;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <CompanyHeaderCard
        company={company}
        normalizationStatus={filing.normalization_status}
        sectorLabel={t("company.sector")}
        notAvailableText={notAvailable}
        backToListLabel={t("backToList")}
        backHref={`/${locale}/companies`}
      />

      <PriceCard
        price={price}
        locale={locale}
        labels={{
          title: t("price.title"),
          close: t("price.close"),
          changeAmount: t("price.changeAmount"),
          changePct: t("price.changePct"),
          volume: t("price.volume"),
          turnover: t("price.turnover"),
          tradesCount: t("price.tradesCount"),
          tradeDate: t("price.tradeDate"),
          source: t("price.source"),
          notAvailable,
          unavailableMessage: t("price.unavailableMessage"),
        }}
      />

      {/* Filing / period section — normalization status now lives in the header card above */}
      <SectionCard title={t("sections.filing")}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
          <div className="flex justify-between items-baseline py-2.5 border-b border-gray-100 dark:border-gray-800 sm:border-b-0 sm:py-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">{t("filing.fiscalYear")}</span>
            <span dir="ltr" className="num text-sm font-semibold text-gray-900 dark:text-gray-100">
              {filing.fiscal_year !== null ? String(filing.fiscal_year) : notAvailable}
            </span>
          </div>
          <div className="flex justify-between items-baseline py-2.5 border-b border-gray-100 dark:border-gray-800 sm:border-b-0 sm:py-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">{t("filing.period")}</span>
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {filing.period ?? notAvailable}
            </span>
          </div>
          <div className="flex justify-between items-baseline py-2.5 border-b border-gray-100 dark:border-gray-800 sm:border-b-0 sm:py-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">{t("filing.periodType")}</span>
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {filing.period_type ?? notAvailable}
            </span>
          </div>
          <FinancialRow
            label={t("filing.reportingScale")}
            value={filing.reporting_scale !== null ? String(filing.reporting_scale) : null}
            locale={locale}
            notAvailableText={notAvailable}
          />
          <div className="flex justify-between items-baseline py-2.5 sm:py-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">{t("filing.isConsolidated")}</span>
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {filing.is_consolidated === null ? notAvailable : filing.is_consolidated ? "✓" : "✗"}
            </span>
          </div>
        </div>
      </SectionCard>

      {/* Balance Sheet / Income Statement / Cash Flow */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SectionCard title={t("sections.balanceSheet")} accent="balanceSheet">
          <FinancialRow
            label={t("balanceSheet.totalAssets")}
            value={balance_sheet.total_assets}
            locale={locale}
            notAvailableText={notAvailable}
            emphasize
          />
          <FinancialRow label={t("balanceSheet.totalLiabilities")} value={balance_sheet.total_liabilities} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("balanceSheet.totalEquity")} value={balance_sheet.equity} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("balanceSheet.cashAndEquivalents")} value={balance_sheet.cash_and_equivalents} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("balanceSheet.shortTermDebt")} value={balance_sheet.short_term_debt} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("balanceSheet.longTermDebt")} value={balance_sheet.long_term_debt} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("balanceSheet.totalDebt")} value={balance_sheet.total_debt} locale={locale} notAvailableText={notAvailable} />
        </SectionCard>

        <SectionCard title={t("sections.incomeStatement")} accent="incomeStatement">
          <FinancialRow label={t("incomeStatement.revenue")} value={income_statement.revenue} locale={locale} notAvailableText={notAvailable} emphasize />
          <FinancialRow label={t("incomeStatement.financeCost")} value={income_statement.finance_cost} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("incomeStatement.profitBeforeTax")} value={income_statement.profit_before_tax} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("incomeStatement.zakatTax")} value={income_statement.zakat_tax} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("incomeStatement.netIncome")} value={income_statement.net_income} locale={locale} notAvailableText={notAvailable} emphasize />
        </SectionCard>

        <SectionCard title={t("sections.cashFlow")} accent="cashFlow">
          <FinancialRow label={t("cashFlow.operatingCashFlow")} value={cash_flow.operating_cash_flow} locale={locale} notAvailableText={notAvailable} emphasize />
          <FinancialRow label={t("cashFlow.investingCashFlow")} value={cash_flow.investing_cash_flow} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("cashFlow.financingCashFlow")} value={cash_flow.financing_cash_flow} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("cashFlow.capex")} value={cash_flow.capex} locale={locale} notAvailableText={notAvailable} />
          <FinancialRow label={t("cashFlow.freeCashFlow")} value={cash_flow.free_cash_flow} locale={locale} notAvailableText={notAvailable} emphasize />
        </SectionCard>
      </div>

      {/* Data Quality */}
      <SectionCard title={t("sections.dataQuality")}>
        <DataQualityPanel
          missingFields={data_quality.missing_fields}
          conflicts={data_quality.conflicts}
          sourceMapAvailable={data_quality.source_map_available}
          sourceMap={data_quality.source_map}
          labels={{
            missingFields: t("dataQuality.missingFields"),
            noMissingFields: t("dataQuality.noMissingFields"),
            conflicts: t("dataQuality.conflicts"),
            noConflicts: t("dataQuality.noConflicts"),
            conflictField: t("dataQuality.conflictField"),
            conflictStatus: t("dataQuality.conflictStatus"),
            conflictCandidates: t("dataQuality.conflictCandidates"),
            sourceMapAvailable: t("dataQuality.sourceMapAvailable"),
            sourceMapUnavailable: t("dataQuality.sourceMapUnavailable"),
            viewSourceDetails: t("dataQuality.viewSourceDetails"),
            hideSourceDetails: t("dataQuality.hideSourceDetails"),
            calculated: t("dataQuality.calculated"),
            formula: t("dataQuality.formula"),
          }}
        />
      </SectionCard>

      {/* Metadata */}
      <SectionCard title={t("sections.metadata")}>
        <div className="flex justify-between items-baseline py-2.5 border-b border-gray-100 dark:border-gray-800">
          <span className="text-sm text-gray-600 dark:text-gray-400">{t("metadata.dataSource")}</span>
          <span className="text-sm font-mono text-gray-900 dark:text-gray-100">{metadata.data_source}</span>
        </div>
        <div className="flex justify-between items-baseline py-2.5 border-b border-gray-100 dark:border-gray-800">
          <span className="text-sm text-gray-600 dark:text-gray-400">{t("metadata.generatedAt")}</span>
          <span className="text-sm text-gray-900 dark:text-gray-100">
            {formatDateTime(metadata.generated_at, locale, notAvailable)}
          </span>
        </div>
        <div className="flex justify-between items-baseline py-2.5">
          <span className="text-sm text-gray-600 dark:text-gray-400">{t("metadata.manualOverride")}</span>
          <span
            className={`text-sm font-semibold ${
              metadata.manual_override ? "text-amber-600 dark:text-amber-400" : "text-gray-500 dark:text-gray-400"
            }`}
          >
            {metadata.manual_override ? t("metadata.manualOverrideYes") : t("metadata.manualOverrideNo")}
          </span>
        </div>
      </SectionCard>

      <div className="pt-2">
        <QuickSampleLinks locale={locale} label={t("backToList")} />
      </div>
    </div>
  );
}
