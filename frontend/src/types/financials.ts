/**
 * Types matching the backend's actual response shapes exactly, verified
 * live against GET /api/v1/companies/ and GET /api/v1/companies/{symbol}/financials.
 *
 * Decimal fields are typed as `string | null` because the backend (Pydantic)
 * serializes Decimal values as JSON strings (e.g. "6200549000.0000"), not
 * numbers. Always parse with parseFinancialNumber() before formatting —
 * never reuse these strings for arithmetic.
 */
import type { ApiMeta } from "@/types";

export interface CompanyListItem {
  id: string;
  symbol: string;
  arabic_name: string;
  english_name: string | null;
  market: string | null;
  sector_ar: string | null;
  sector_en: string | null;
  mapping_status: string;
  data_status: string;
}

export interface CompaniesListResponse {
  success: boolean;
  data: CompanyListItem[];
  total: number;
  page: number;
  per_page: number;
  meta: ApiMeta;
}

export interface FinancialsCompanySection {
  symbol: string;
  name_ar: string;
  name_en: string | null;
  market: string | null;
  sector_ar: string | null;
  sector_en: string | null;
}

export interface FinancialsFilingSection {
  fiscal_year: number | null;
  period: string | null;
  period_type: string | null;
  reporting_scale: number | null;
  is_consolidated: boolean | null;
  normalization_status: string;
}

export interface FinancialsBalanceSheetSection {
  total_assets: string | null;
  total_liabilities: string | null;
  equity: string | null;
  cash_and_equivalents: string | null;
  short_term_debt: string | null;
  long_term_debt: string | null;
  total_debt: string | null;
}

export interface FinancialsIncomeStatementSection {
  revenue: string | null;
  finance_cost: string | null;
  profit_before_tax: string | null;
  zakat_tax: string | null;
  net_income: string | null;
}

export interface FinancialsCashFlowSection {
  operating_cash_flow: string | null;
  investing_cash_flow: string | null;
  financing_cash_flow: string | null;
  capex: string | null;
  free_cash_flow: string | null;
}

export interface ConflictSummary {
  field_name: string;
  resolution_status: string;
  candidate_count: number;
}

export interface FinancialsDataQualitySection {
  missing_fields: string[];
  conflict_count: number;
  conflicts: ConflictSummary[];
  source_map_available: boolean;
  source_map: Record<string, Record<string, unknown>> | null;
}

export interface FinancialsMetadataSection {
  generated_at: string;
  data_source: string;
  manual_override: boolean;
}

export interface CompanyFinancialsOut {
  company: FinancialsCompanySection;
  filing: FinancialsFilingSection;
  balance_sheet: FinancialsBalanceSheetSection;
  income_statement: FinancialsIncomeStatementSection;
  cash_flow: FinancialsCashFlowSection;
  data_quality: FinancialsDataQualitySection;
  metadata: FinancialsMetadataSection;
}

export interface CompanyFinancialsResponse {
  success: boolean;
  data: CompanyFinancialsOut | null;
  meta: ApiMeta;
}

/** The 6 sample symbols this MVP is verified against. */
export const QUICK_SAMPLE_SYMBOLS = ["2240", "2222", "2020", "4263", "2050", "1120"] as const;
