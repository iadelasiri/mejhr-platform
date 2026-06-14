import { getTranslations } from "next-intl/server";
import { useTranslations } from "next-intl";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("dataQuality");
  return { title: t("title") };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchDataQuality() {
  try {
    const res = await fetch(`${API_URL}/api/v1/data-quality/`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function MetricCard({
  label,
  value,
}: {
  label: string;
  value: number | string | null | undefined;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
      <div className="text-xl font-bold text-mejhr-700 dark:text-mejhr-300 num">
        {value ?? "—"}
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{label}</div>
    </div>
  );
}

export default async function DataQualityPage() {
  const t = await getTranslations("dataQuality");
  const data = await fetchDataQuality();

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("subtitle")}</p>
      </div>

      {!data ? (
        <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-xl p-8 text-center">
          <p className="font-medium text-amber-800 dark:text-amber-200">{t("noData")}</p>
        </div>
      ) : (
        <>
          {/* Companies */}
          <section>
            <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
              {t("companies")}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="Total" value={data.companies?.total} />
              <MetricCard label="Sector Mapped" value={data.companies?.sector_mapped} />
              <MetricCard label="Pending Official Mapping" value={data.companies?.pending_official_sector_mapping} />
              <MetricCard label="Sample (not official)" value={data.companies?.sample_not_official} />
            </div>
          </section>

          {/* XBRL */}
          <section>
            <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
              {t("filings")}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <MetricCard label="Filings Discovered" value={data.xbrl?.filings_discovered} />
              <MetricCard label="Files Downloaded" value={data.xbrl?.files_downloaded} />
              <MetricCard label="Files Rendered" value={data.xbrl?.files_rendered} />
              <MetricCard label="Raw Items" value={data.xbrl?.raw_items_total} />
              <MetricCard label="Announcements w/ XBRL" value={data.announcements?.with_xbrl} />
            </div>
          </section>

          {/* Financials */}
          <section>
            <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
              {t("financials")}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="Normalized Filings" value={data.financials?.normalized_filings} />
              <MetricCard label="With Revenue" value={data.financials?.with_revenue} />
              <MetricCard label="With Net Income" value={data.financials?.with_net_income} />
              <MetricCard label="With Equity" value={data.financials?.with_equity} />
            </div>
          </section>

          {/* Ratios */}
          <section>
            <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
              {t("ratios")}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="Total" value={data.ratios?.total} />
              <MetricCard label="With ROIC" value={data.ratios?.with_roic} />
              <MetricCard label="With EV/IC" value={data.ratios?.with_ev_ic} />
              <MetricCard label="Screener Rows" value={data.screener?.snapshot_rows} />
            </div>
          </section>

          {data.notes && (
            <p className="text-xs text-gray-400 dark:text-gray-600 border-t border-gray-100 dark:border-gray-800 pt-4">
              {data.notes}
            </p>
          )}
        </>
      )}
    </div>
  );
}
