export interface ApiMeta {
  data_source: string;
  pipeline_status: "not_configured" | "populated" | "empty";
  message?: string;
  sample_data: boolean;
  last_updated?: string;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  per_page: number;
  meta: ApiMeta;
}

export interface SingleResponse<T> {
  success: boolean;
  data: T | null;
  meta: ApiMeta;
}

export interface Sector {
  id: string;
  code: string | null;
  arabic_name: string;
  english_name: string | null;
  market: string | null;
}

export interface Company {
  id: string;
  symbol: string;
  arabic_name: string;
  english_name: string | null;
  market: string | null;
  sector?: Sector | null;
  mapping_status: string;
  data_status: string;
  source: string | null;
  source_url: string | null;
  last_updated: string | null;
  imported_at: string | null;
}

export interface ScreenerRow {
  id: string;
  symbol: string;
  company_name_ar: string | null;
  company_name_en: string | null;
  market: string | null;
  sector_ar: string | null;
  sector_en: string | null;
  latest_price: string | null;
  change_pct: string | null;
  market_cap: string | null;
  revenue: string | null;
  net_income: string | null;
  roic: string | null;
  ev_ic: string | null;
  pe: string | null;
  pb: string | null;
  ps: string | null;
  debt_equity: string | null;
  fcf: string | null;
  price_source: string | null;
  financial_source: string | null;
  last_price_update: string | null;
  last_financial_update: string | null;
  data_quality_status: string;
}

export interface ImportJob {
  id: string;
  job_type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  stats: Record<string, unknown> | null;
  triggered_by: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: "admin" | "user";
  plan: "free" | "pro";
  is_active: boolean;
  created_at: string;
}
