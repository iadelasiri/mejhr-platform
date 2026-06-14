import { useTranslations } from "next-intl";
import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("home");
  return { title: t("title") };
}

function StatCard({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
      <div className="text-2xl font-bold text-mejhr-700 dark:text-mejhr-200 num">{value}</div>
      <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mt-1">{label}</div>
      {note && <div className="text-xs text-gray-400 mt-1">{note}</div>}
    </div>
  );
}

function DataRuleItem({ text }: { text: string }) {
  return (
    <li className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
      <span className="mt-1 w-4 h-4 rounded-full bg-mejhr-100 dark:bg-mejhr-900 flex items-center justify-center flex-shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-mejhr-500" />
      </span>
      {text}
    </li>
  );
}

export default function HomePage() {
  const t = useTranslations("home");
  const tc = useTranslations("common");

  return (
    <div className="max-w-6xl mx-auto px-4 py-10 space-y-12">
      {/* Hero */}
      <section className="text-center space-y-4 pt-4">
        <h1 className="text-4xl font-bold tracking-tight text-gray-900 dark:text-white">
          {t("title")}
        </h1>
        <p className="text-lg text-gray-500 dark:text-gray-400 max-w-2xl mx-auto">
          {t("subtitle")}
        </p>
      </section>

      {/* Stats */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Companies" value="0" note="Run pipeline to populate" />
        <StatCard label="XBRL Filings" value="0" note="Phase 2" />
        <StatCard label="Normalized Financials" value="0" note="Phase 2" />
        <StatCard label="Screener Rows" value="0" note="Phase 2" />
      </section>

      {/* Pipeline Status */}
      <section className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-xl p-6 space-y-2">
        <div className="flex items-center gap-2">
          <span className="status-dot status-dot-yellow" />
          <h2 className="font-semibold text-amber-800 dark:text-amber-200">{t("pipelineStatus")}</h2>
        </div>
        <p className="text-amber-700 dark:text-amber-300 font-medium">{t("notConfigured")}</p>
        <p className="text-amber-600 dark:text-amber-400 text-sm">{t("notConfiguredDesc")}</p>
      </section>

      {/* Data Rules */}
      <section className="bg-gray-50 dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-4">{t("dataRules")}</h2>
        <ul className="space-y-2">
          <DataRuleItem text={t("rule1")} />
          <DataRuleItem text={t("rule2")} />
          <DataRuleItem text={t("rule3")} />
          <DataRuleItem text={t("rule4")} />
          <DataRuleItem text={t("rule5")} />
        </ul>
      </section>
    </div>
  );
}
