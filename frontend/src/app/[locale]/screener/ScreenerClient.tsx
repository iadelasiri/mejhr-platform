"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { CompanyListItem } from "@/types/financials";

interface Labels {
  searchPlaceholder: string;
  sectorLabel: string;
  allSectors: string;
  mappingStatusLabel: string;
  allStatuses: string;
  resetLabel: string;
  tabAll: string;
  tabMapped: string;
  tabUnmapped: string;
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

type MappingFilter = "all" | "mapped" | "unmapped_sector";

/**
 * Tadawul-only company screener table. Search/sector/mapping-status filter
 * entirely client-side over the already-fetched bulk company list — no
 * per-row API calls. The "view" tabs are presets over the same
 * mapping-status state (not a separate dimension), since mapping_status is
 * the only bulk-available data-quality-adjacent signal today.
 */
export default function ScreenerClient({
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
  const [sector, setSector] = useState("all");
  const [mappingStatus, setMappingStatus] = useState<MappingFilter>("all");

  const sectors = useMemo(() => {
    const set = new Set<string>();
    for (const c of companies) {
      const label = c.sector_ar ?? c.sector_en;
      if (label) set.add(label);
    }
    return Array.from(set).sort();
  }, [companies]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return companies.filter((c) => {
      if (term) {
        const matches =
          c.symbol.toLowerCase().includes(term) ||
          c.arabic_name.toLowerCase().includes(term) ||
          (c.english_name ?? "").toLowerCase().includes(term);
        if (!matches) return false;
      }
      if (sector !== "all") {
        const label = c.sector_ar ?? c.sector_en;
        if (label !== sector) return false;
      }
      if (mappingStatus !== "all" && c.mapping_status !== mappingStatus) {
        return false;
      }
      return true;
    });
  }, [companies, search, sector, mappingStatus]);

  const resetFilters = () => {
    setSearch("");
    setSector("all");
    setMappingStatus("all");
  };

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 p-8 text-center space-y-2">
        <h2 className="font-semibold text-red-700 dark:text-red-300">{labels.loadError}</h2>
        <p className="text-sm text-red-600 dark:text-red-400">{labels.loadErrorDesc}</p>
        <p className="text-xs text-red-400 dark:text-red-500 font-mono mt-2">{error}</p>
      </div>
    );
  }

  const tabs: { id: MappingFilter; label: string }[] = [
    { id: "all", label: labels.tabAll },
    { id: "mapped", label: labels.tabMapped },
    { id: "unmapped_sector", label: labels.tabUnmapped },
  ];

  return (
    <div className="space-y-3">
      {/* View tabs */}
      <div className="flex gap-1 overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-1.5">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setMappingStatus(tab.id)}
            className={`flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              mappingStatus === tab.id
                ? "bg-mejhr-50 dark:bg-mejhr-950 text-mejhr-700 dark:text-mejhr-300"
                : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Filter command row */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-3 flex flex-wrap items-center gap-2.5">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={labels.searchPlaceholder}
          className="flex-1 min-w-[200px] px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-mejhr-500"
        />

        <label className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
          <span className="text-gray-500 dark:text-gray-400 whitespace-nowrap">{labels.sectorLabel}</span>
          <select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="bg-transparent text-gray-900 dark:text-gray-100 outline-none"
          >
            <option value="all">{labels.allSectors}</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
          <span className="text-gray-500 dark:text-gray-400 whitespace-nowrap">{labels.mappingStatusLabel}</span>
          <select
            value={mappingStatus}
            onChange={(e) => setMappingStatus(e.target.value as MappingFilter)}
            className="bg-transparent text-gray-900 dark:text-gray-100 outline-none"
          >
            <option value="all">{labels.allStatuses}</option>
            <option value="mapped">{labels.tabMapped}</option>
            <option value="unmapped_sector">{labels.tabUnmapped}</option>
          </select>
        </label>

        <button
          type="button"
          onClick={resetFilters}
          className="px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          {labels.resetLabel}
        </button>

        <span dir="ltr" className="num text-xs text-gray-400 ms-auto whitespace-nowrap">
          {filtered.length} / {companies.length}
        </span>
      </div>

      {/* Table */}
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
                  <th className="px-3 py-2 text-start font-medium text-xs uppercase tracking-wide">{labels.colSymbol}</th>
                  <th className="px-3 py-2 text-start font-medium text-xs uppercase tracking-wide">{labels.colNameAr}</th>
                  <th className="px-3 py-2 text-start font-medium text-xs uppercase tracking-wide">{labels.colNameEn}</th>
                  <th className="px-3 py-2 text-start font-medium text-xs uppercase tracking-wide">{labels.colSector}</th>
                  <th className="px-3 py-2 text-start font-medium text-xs uppercase tracking-wide">{labels.colMarket}</th>
                  <th className="px-3 py-2 text-start font-medium text-xs uppercase tracking-wide">{labels.colMappingStatus}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {filtered.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-50 dark:hover:bg-gray-900/50">
                    <td className="px-3 py-1.5">
                      <Link
                        href={`/${locale}/companies/${c.symbol}`}
                        className="font-mono font-semibold text-mejhr-600 dark:text-mejhr-400 hover:underline"
                      >
                        {c.symbol}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 text-gray-900 dark:text-gray-100">
                      <Link href={`/${locale}/companies/${c.symbol}`} className="hover:underline">
                        {c.arabic_name}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 text-gray-600 dark:text-gray-400">
                      {c.english_name ?? labels.notAvailable}
                    </td>
                    <td className="px-3 py-1.5 text-gray-500 dark:text-gray-400">
                      {c.sector_ar ?? c.sector_en ?? labels.notAvailable}
                    </td>
                    <td className="px-3 py-1.5">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-mejhr-50 dark:bg-mejhr-950 text-mejhr-700 dark:text-mejhr-300">
                        {c.market ?? labels.notAvailable}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-gray-500 dark:text-gray-400 text-xs">{c.mapping_status}</td>
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
