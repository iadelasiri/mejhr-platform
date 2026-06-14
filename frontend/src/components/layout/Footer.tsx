import { useTranslations } from "next-intl";
import Link from "next/link";

export default function Footer() {
  const t = useTranslations("brand");

  return (
    <footer className="border-t border-gray-200 dark:border-gray-800 py-6 mt-8">
      <div className="max-w-screen-2xl mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-gray-400 dark:text-gray-600">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-mejhr-600 flex items-center justify-center">
            <span className="text-white font-bold text-[10px]">M</span>
          </div>
          <span className="font-semibold text-gray-600 dark:text-gray-400">{t("name")}</span>
          <span>—</span>
          <span>{t("tagline")}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs">Data source: Saudi Exchange (official)</span>
          <Link href="/en/data-quality" className="hover:text-gray-600 dark:hover:text-gray-400 transition-colors text-xs">
            Data Quality
          </Link>
          <Link href="/en/api-docs" className="hover:text-gray-600 dark:hover:text-gray-400 transition-colors text-xs">
            API
          </Link>
        </div>
      </div>
    </footer>
  );
}
