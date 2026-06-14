import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchCompany(symbol: string) {
  try {
    const res = await fetch(`${API_URL}/api/v1/companies/${symbol}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return res.json();
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

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex justify-between py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">
      <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-900 dark:text-white">{value ?? "—"}</span>
    </div>
  );
}

export default async function CompanyPage({
  params,
}: {
  params: { symbol: string; locale: string };
}) {
  const t = await getTranslations("company");
  const symbol = params.symbol.toUpperCase();
  const result = await fetchCompany(symbol);

  if (!result?.data) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center space-y-3">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">{t("notFound")}</h1>
        <p className="text-gray-400 text-sm">Symbol: {symbol}</p>
        <p className="text-sm text-amber-600 dark:text-amber-400 max-w-md mx-auto">
          No official Saudi Exchange company data imported yet. Run the Saudi Exchange
          connectivity test and companies refresh job.
        </p>
        <Link
          href="../screener"
          className="inline-block mt-2 text-sm text-mejhr-600 hover:underline"
        >
          Back to Screener
        </Link>
      </div>
    );
  }

  const company = result.data;
  const isSample = company.data_status === "sample_not_official";

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      {isSample && (
        <div className="sample-banner rounded-xl">
          SAMPLE DATA — NOT OFFICIAL — For UI testing only
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{symbol}</h1>
            <span className="text-xs px-2 py-0.5 bg-mejhr-100 dark:bg-mejhr-900 text-mejhr-700 dark:text-mejhr-300 rounded-full">
              {company.market ?? "—"}
            </span>
          </div>
          <p className="text-lg text-gray-700 dark:text-gray-300 mt-1">{company.arabic_name}</p>
          {company.english_name && (
            <p className="text-sm text-gray-500 dark:text-gray-400">{company.english_name}</p>
          )}
        </div>
        <Link
          href={`/company/${symbol}/statements`}
          className="text-sm px-4 py-2 border border-mejhr-500 text-mejhr-600 dark:text-mejhr-400 rounded-lg hover:bg-mejhr-50 dark:hover:bg-mejhr-950 transition-colors"
        >
          Statements
        </Link>
      </div>

      {/* Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-3">{t("overview")}</h2>
          <InfoRow label={t("market")} value={company.market} />
          <InfoRow label={t("sector")} value={company.sector?.arabic_name ?? "—"} />
          <InfoRow label={t("mappingStatus")} value={company.mapping_status} />
          <InfoRow label={t("dataStatus")} value={company.data_status} />
          {company.source_url && (
            <div className="mt-3">
              <a
                href={company.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-mejhr-600 hover:underline"
              >
                View on Saudi Exchange →
              </a>
            </div>
          )}
        </div>

        {/* Price placeholder */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-3">Market Data</h2>
          <div className="text-center py-6 text-gray-400 text-sm">
            No price data — run fetch_prices pipeline
          </div>
        </div>
      </div>

      {/* Financials placeholder */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-3">{t("financials")}</h2>
        <div className="text-center py-8 text-gray-400 text-sm">
          No financial data — run XBRL pipeline (Phase 2)
        </div>
      </div>
    </div>
  );
}
