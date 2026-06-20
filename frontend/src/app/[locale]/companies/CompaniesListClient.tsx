"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { CompanyListItem } from "@/types/financials";

interface Labels {
  searchPlaceholder: string;
  colSymbol: string;
  colNameAr: string;
  colNameEn: string;
  colMarket: string;
  colSector: string;
  colMappingStatus: string;
  noResults: string;
  noResultsDesc: string;
  loadError: string;
  loadErrorDesc: string;
  notAvailable: string;
}

export default function CompaniesListClient({
  companies,
  error,
  locale,
  labels,
}: {
  companies: CompanyListItem[];
  error: string | null;
  locale: string;
  labels: Labels;
}) {
  const [search, setSearch] = useState("");

  // Main Market (Tadawul) only — fetchAllCompanies() never fetches Nomu,
  // so there is nothing here to filter by market. Search-only.
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return companies;
    return companies.filter(
      (c) =>
        c.symbol.toLowerCase().includes(term) ||
        c.arabic_name.toLowerCase().includes(term) ||
        (c.english_name ?? "").toLowerCase().includes(term),
    );
  }, [companies, search]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 p-8 text-center space-y-2">
        <h2 className="font-semibold text-red-700 dark:text-red-300">{labels.loadError}</h2>
        <p className="text-sm text-red-600 dark:text-red-400">{labels.loadErrorDesc}</p>
        <p className="text-xs text-red-400 dark:text-red-500 font-mono mt-2">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={labels.searchPlaceholder}
        className="w-full px-4 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-mejhr-500"
      />

      <div className="text-xs text-gray-400 num">
        {filtered.length} / {companies.length}
      </div>

      {/* Results */}
      {filtered.length === 0 ? (
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 p-12 text-center space-y-1">
          <p className="text-gray-600 dark:text-gray-300 font-medium">{labels.noResults}</p>
          <p className="text-sm text-gray-400">{labels.noResultsDesc}</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900 text-gray-500 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3 text-start font-medium">{labels.colSymbol}</th>
                  <th className="px-4 py-3 text-start font-medium">{labels.colNameAr}</th>
                  <th className="px-4 py-3 text-start font-medium">{labels.colNameEn}</th>
                  <th className="px-4 py-3 text-start font-medium">{labels.colMarket}</th>
                  <th className="px-4 py-3 text-start font-medium">{labels.colSector}</th>
                  <th className="px-4 py-3 text-start font-medium">{labels.colMappingStatus}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {filtered.map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-3">
                      <Link
                        href={`/${locale}/companies/${c.symbol}`}
                        className="font-mono font-semibold text-mejhr-600 dark:text-mejhr-400 hover:underline"
                      >
                        {c.symbol}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-gray-900 dark:text-gray-100">
                      <Link href={`/${locale}/companies/${c.symbol}`} className="hover:underline">
                        {c.arabic_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                      {c.english_name ?? labels.notAvailable}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-mejhr-50 dark:bg-mejhr-950 text-mejhr-700 dark:text-mejhr-300">
                        {c.market ?? labels.notAvailable}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {c.sector_ar ?? c.sector_en ?? labels.notAvailable}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 text-xs">
                      {c.mapping_status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
