import { getTranslations } from "next-intl/server";
import { useTranslations } from "next-intl";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("sectors");
  return { title: t("title") };
}

export default function SectorsPage() {
  const t = useTranslations("sectors");

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("subtitle")}</p>
      </div>

      <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-xl p-8 text-center">
        <p className="font-medium text-amber-800 dark:text-amber-200">{t("noData")}</p>
        <p className="text-sm text-amber-600 dark:text-amber-400 mt-1">{t("noDataDesc")}</p>
      </div>
    </div>
  );
}
