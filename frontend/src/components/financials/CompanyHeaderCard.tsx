import Link from "next/link";
import StatusBadge from "@/components/financials/StatusBadge";
import type { FinancialsCompanySection } from "@/types/financials";

/**
 * Company identity card — symbol, names, market, sector, and the
 * normalization status badge surfaced prominently right next to the
 * symbol (the single most important trust signal on the page), rather
 * than buried inside the filing details table.
 */
export default function CompanyHeaderCard({
  company,
  normalizationStatus,
  sectorLabel,
  notAvailableText,
  backToListLabel,
  backHref,
}: {
  company: FinancialsCompanySection;
  normalizationStatus: string;
  sectorLabel: string;
  notAvailableText: string;
  backToListLabel: string;
  backHref: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{company.symbol}</h1>
            {company.market && (
              <span className="text-xs px-2 py-0.5 bg-mejhr-100 dark:bg-mejhr-900 text-mejhr-700 dark:text-mejhr-300 rounded-full">
                {company.market}
              </span>
            )}
            <StatusBadge status={normalizationStatus} size="sm" />
          </div>
          <p className="text-lg text-gray-700 dark:text-gray-300 mt-1.5">{company.name_ar}</p>
          {company.name_en && <p className="text-sm text-gray-500 dark:text-gray-400">{company.name_en}</p>}
          <p className="text-xs text-gray-400 mt-2">
            {sectorLabel}: {company.sector_ar ?? company.sector_en ?? notAvailableText}
          </p>
        </div>
        <Link
          href={backHref}
          className="text-sm px-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors whitespace-nowrap"
        >
          {backToListLabel}
        </Link>
      </div>
    </div>
  );
}
