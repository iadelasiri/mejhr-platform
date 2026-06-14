import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("apiDocs");
  return { title: t("title") };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ENDPOINTS = [
  { method: "GET", path: "/api/v1/health/", desc: "Platform health check (DB, Redis, worker status)" },
  { method: "POST", path: "/api/v1/auth/login", desc: "Login with email and password → JWT tokens" },
  { method: "POST", path: "/api/v1/auth/register", desc: "Register new user account" },
  { method: "GET", path: "/api/v1/auth/me", desc: "Get current authenticated user (requires JWT)" },
  { method: "GET", path: "/api/v1/companies/", desc: "List all companies (paginated, filterable)" },
  { method: "GET", path: "/api/v1/companies/{symbol}", desc: "Get single company by symbol" },
  { method: "GET", path: "/api/v1/screener/", desc: "Screener — reads from snapshot table only" },
  { method: "GET", path: "/api/v1/sectors/", desc: "List official sectors and industry groups" },
  { method: "GET", path: "/api/v1/announcements/", desc: "List announcements (searchable)" },
  { method: "GET", path: "/api/v1/data-quality/", desc: "Data quality metrics and pipeline status" },
  { method: "GET", path: "/api/v1/jobs/", desc: "List import jobs (admin only)" },
  { method: "POST", path: "/api/v1/jobs/trigger", desc: "Trigger a pipeline job (admin only)" },
];

const METHOD_COLORS: Record<string, string> = {
  GET: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  POST: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
};

export default async function ApiDocsPage() {
  const t = await getTranslations("apiDocs");

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("subtitle")}</p>
      </div>

      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <div className="text-xs text-gray-500 dark:text-gray-400 font-medium mb-1">{t("baseUrl")}</div>
        <code className="text-sm font-mono text-mejhr-700 dark:text-mejhr-300">{API_URL}/api/v1</code>
        <div className="text-xs text-gray-400 mt-2">
          Interactive docs: <code className="text-mejhr-600">{API_URL}/api/docs</code> (development only)
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
          {t("endpoints")}
        </h2>
        <div className="divide-y divide-gray-100 dark:divide-gray-800 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          {ENDPOINTS.map((ep) => (
            <div
              key={ep.path}
              className="flex items-start gap-4 px-4 py-3 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <span
                className={`text-xs font-bold px-2 py-0.5 rounded font-mono mt-0.5 flex-shrink-0 ${METHOD_COLORS[ep.method] ?? ""}`}
              >
                {ep.method}
              </span>
              <div className="min-w-0">
                <code className="text-sm font-mono text-gray-800 dark:text-gray-200 break-all">
                  {ep.path}
                </code>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{ep.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="text-xs text-gray-400 dark:text-gray-600 space-y-1">
        <p>• All responses include <code>meta.data_source</code>, <code>meta.pipeline_status</code>, and <code>meta.sample_data</code> fields.</p>
        <p>• All list endpoints support <code>page</code> and <code>per_page</code> query parameters.</p>
        <p>• Missing data is returned as <code>null</code> — never fabricated.</p>
        <p>• Admin endpoints require <code>Authorization: Bearer &lt;token&gt;</code> with admin role.</p>
      </div>
    </div>
  );
}
