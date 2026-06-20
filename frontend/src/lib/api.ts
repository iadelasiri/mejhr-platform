// API_INTERNAL_URL (server-only, not NEXT_PUBLIC_-prefixed) takes priority
// when this code runs server-side inside Docker, where "localhost" refers
// to the frontend container itself, not the backend container. In the
// browser, API_INTERNAL_URL is always undefined (stripped from the client
// bundle), so this correctly falls through to NEXT_PUBLIC_API_URL there.
const API_BASE =
  process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ApiMeta {
  data_source: string;
  pipeline_status: string;
  message?: string;
  sample_data: boolean;
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

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined"
    ? localStorage.getItem("mejhr_access_token")
    : null;

  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error ${res.status}`);
  }

  return res.json();
}

export const api = {
  health: () => apiFetch<Record<string, unknown>>("/health/"),

  companies: (params?: Record<string, string | number>) => {
    const q = params ? "?" + new URLSearchParams(params as Record<string, string>).toString() : "";
    return apiFetch<PaginatedResponse<unknown>>(`/companies/${q}`);
  },

  company: (symbol: string) =>
    apiFetch<SingleResponse<unknown>>(`/companies/${symbol}`),

  companyFinancials: (symbol: string, params?: { fiscal_year?: number; fiscal_period?: string }) => {
    const q = params
      ? "?" + new URLSearchParams(params as unknown as Record<string, string>).toString()
      : "";
    return apiFetch<import("@/types/financials").CompanyFinancialsResponse>(
      `/companies/${symbol}/financials${q}`,
    );
  },

  marketIndicesLatest: (params?: { page?: number; per_page?: number }) => {
    const q = params
      ? "?" + new URLSearchParams(params as unknown as Record<string, string>).toString()
      : "";
    return apiFetch<import("@/types/prices").IndexPricesListResponse>(`/market/indices/latest${q}`);
  },

  screener: (params?: Record<string, string | number>) => {
    const q = params ? "?" + new URLSearchParams(params as Record<string, string>).toString() : "";
    return apiFetch<PaginatedResponse<unknown>>(`/screener/${q}`);
  },

  sectors: () => apiFetch<PaginatedResponse<unknown>>("/sectors/"),

  announcements: (params?: Record<string, string | number>) => {
    const q = params ? "?" + new URLSearchParams(params as Record<string, string>).toString() : "";
    return apiFetch<PaginatedResponse<unknown>>(`/announcements/${q}`);
  },

  dataQuality: () => apiFetch<Record<string, unknown>>("/data-quality/"),

  jobs: () => apiFetch<PaginatedResponse<unknown>>("/jobs/"),

  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; refresh_token: string; user: unknown }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => apiFetch<unknown>("/auth/me"),
};
