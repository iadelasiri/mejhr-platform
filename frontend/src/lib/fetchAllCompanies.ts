import { api } from "@/lib/api";
import type { CompaniesListResponse, CompanyListItem } from "@/types/financials";

// Tadawul (Main Market) only. Nomu (the parallel/secondary market) is
// intentionally excluded from this MVP entirely — not fetched, not
// filterable, never displayed. REITs are already classified as
// market="tadawul" in the database (they trade on the Main Market), so
// they remain included automatically without any special-casing here.
const MARKET = "tadawul";
const MAX_PER_PAGE = 200;

/**
 * Fetch every Main Market (Tadawul) company using only the existing
 * GET /api/v1/companies/ endpoint (paginated, max per_page=200). No new
 * backend endpoint or query parameter is introduced — this just calls the
 * existing list endpoint as many times as needed to cover all pages and
 * combines the results so the companies list page can offer instant
 * client-side search.
 *
 * Returns an empty array (never throws) if the backend is unreachable —
 * callers render the error/empty state based on `error`.
 */
export async function fetchAllCompanies(): Promise<{
  companies: CompanyListItem[];
  error: string | null;
}> {
  try {
    const allCompanies: CompanyListItem[] = [];

    const first = (await api.companies({
      market: MARKET,
      page: 1,
      per_page: MAX_PER_PAGE,
    })) as CompaniesListResponse;

    allCompanies.push(...first.data);

    const totalPages = Math.ceil(first.total / MAX_PER_PAGE);
    if (totalPages > 1) {
      const remainingPages = await Promise.all(
        Array.from({ length: totalPages - 1 }, (_, i) =>
          api.companies({ market: MARKET, page: i + 2, per_page: MAX_PER_PAGE }) as Promise<CompaniesListResponse>,
        ),
      );
      for (const page of remainingPages) {
        allCompanies.push(...page.data);
      }
    }

    return { companies: allCompanies, error: null };
  } catch (err) {
    return {
      companies: [],
      error: err instanceof Error ? err.message : "Unknown error",
    };
  }
}
