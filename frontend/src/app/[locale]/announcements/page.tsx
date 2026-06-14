import { getTranslations } from "next-intl/server";
import { useTranslations } from "next-intl";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("announcements");
  return { title: t("title") };
}

export default function AnnouncementsPage() {
  const t = useTranslations("announcements");

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("subtitle")}</p>
      </div>

      {/* Filters */}
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <div className="flex flex-wrap gap-3">
          {Object.values(t.raw("filters")).map((label) => (
            <input
              key={label as string}
              type="text"
              placeholder={label as string}
              disabled
              className="h-9 px-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-400 w-36"
            />
          ))}
        </div>
      </div>

      {/* Empty state */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-12 text-center">
        <p className="font-medium text-gray-500 dark:text-gray-400">{t("noData")}</p>
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">{t("noDataDesc")}</p>
      </div>
    </div>
  );
}
