import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin");
  return { title: t("title") };
}

const PIPELINE_JOBS = [
  { id: "fetch_companies", label: "Fetch Companies", phase: 2 },
  { id: "fetch_sectors", label: "Fetch Sectors", phase: 2 },
  { id: "fetch_prices", label: "Fetch Prices", phase: 2 },
  { id: "fetch_announcements", label: "Fetch Announcements", phase: 2 },
  { id: "xbrl_discovery", label: "XBRL Discovery", phase: 2 },
  { id: "xbrl_download", label: "XBRL Download", phase: 2 },
  { id: "xbrl_render", label: "XBRL Render (Playwright)", phase: 2 },
  { id: "xbrl_parse", label: "XBRL Parse", phase: 2 },
  { id: "normalize", label: "Normalize Financials", phase: 2 },
  { id: "calculate_ratios", label: "Calculate Ratios", phase: 2 },
  { id: "build_screener", label: "Build Screener Snapshot", phase: 2 },
  { id: "build_quality_report", label: "Build Data Quality Report", phase: 2 },
];

export default async function AdminPage() {
  const t = await getTranslations("admin");

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Platform administration — requires admin role
        </p>
      </div>

      {/* Phase 2 Pipeline Jobs */}
      <section className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl">
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="font-semibold text-gray-900 dark:text-white">Pipeline Jobs</h2>
          <p className="text-xs text-gray-400 mt-0.5">Phase 2 — Data pipeline not yet configured</p>
        </div>
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {PIPELINE_JOBS.map((job) => (
            <div key={job.id} className="flex items-center justify-between px-5 py-3">
              <div>
                <div className="text-sm font-medium text-gray-800 dark:text-gray-200">{job.label}</div>
                <div className="text-xs text-gray-400 font-mono">{job.id}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                  Phase {job.phase}
                </span>
                <button
                  disabled
                  className="text-xs px-3 py-1.5 bg-mejhr-600 text-white rounded-lg opacity-40 cursor-not-allowed"
                >
                  Run
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Recent Jobs */}
      <section className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl">
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="font-semibold text-gray-900 dark:text-white">{t("jobs")}</h2>
        </div>
        <div className="px-5 py-12 text-center text-gray-400 text-sm">{t("noJobs")}</div>
      </section>

      {/* Quick Links */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "API Health", href: "/api/v1/health/" },
          { label: "API Docs", href: "/api/docs" },
          { label: "Data Quality", href: "/data-quality" },
          { label: "Companies", href: "/companies" },
        ].map((link) => (
          <a
            key={link.label}
            href={link.href}
            target={link.href.startsWith("/api") ? "_blank" : undefined}
            className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 text-center text-sm font-medium text-mejhr-600 dark:text-mejhr-400 hover:bg-mejhr-50 dark:hover:bg-mejhr-950 transition-colors"
          >
            {link.label}
          </a>
        ))}
      </section>
    </div>
  );
}
