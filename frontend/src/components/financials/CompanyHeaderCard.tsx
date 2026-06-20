import StatusBadge from "@/components/financials/StatusBadge";
import type { FinancialsCompanySection } from "@/types/financials";

/**
 * Company identity + price hero card. Identity sits at the flex start,
 * the price ticker at the flex end — with `justify-between` this mirrors
 * automatically under RTL (Arabic: price visually on the left; English:
 * price visually on the right) without any locale branching here.
 * "Back to companies" lives as a breadcrumb above this card, not inside
 * it — kept separate from the company's own identity/price hero.
 */
export default function CompanyHeaderCard({
  company,
  normalizationStatus,
  sectorLabel,
  notAvailableText,
  priceTicker,
}: {
  company: FinancialsCompanySection;
  normalizationStatus: string;
  sectorLabel: string;
  notAvailableText: string;
  priceTicker: React.ReactNode;
}) {
  return (
    <div id="summary" className="scroll-mt-28 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
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
        {priceTicker}
      </div>
    </div>
  );
}
