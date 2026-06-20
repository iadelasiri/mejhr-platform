/**
 * Types matching GET /companies/{symbol}/prices/latest and
 * GET /market/indices/latest exactly, as verified live against the backend.
 *
 * Decimal fields are typed as `string | null` — Pydantic serializes Decimal
 * as a JSON string, never a number. Always parse with parseFinancialNumber()
 * / formatPriceValue() before display — never reuse these strings for
 * arithmetic.
 */
import type { ApiMeta } from "@/types";

export interface CompanyPriceOut {
  symbol: string;
  trade_date: string;
  close: string | null;
  change_amount: string | null;
  change_pct: string | null;
  volume: string | null;
  turnover: string | null;
  trades_count: string | null;
  source: string | null;
  source_url: string | null;
}

export interface CompanyPriceResponse {
  success: boolean;
  data: CompanyPriceOut | null;
  meta: ApiMeta;
}

export interface IndexPriceOut {
  index_code: string;
  index_name_ar: string | null;
  index_name_en: string | null;
  trade_date: string;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string | null;
  previous_close: string | null;
  change_amount: string | null;
  change_pct: string | null;
  volume: string | null;
  turnover: string | null;
  trades_count: string | null;
  trade_date_derivation: string | null;
  source: string | null;
  source_url: string | null;
}

export interface IndexPricesListResponse {
  success: boolean;
  data: IndexPriceOut[];
  total: number;
  page: number;
  per_page: number;
  meta: ApiMeta;
}
