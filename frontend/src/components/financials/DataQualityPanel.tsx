"use client";

import { useState } from "react";
import type { ConflictSummary } from "@/types/financials";

interface Labels {
  missingFields: string;
  noMissingFields: string;
  conflicts: string;
  noConflicts: string;
  conflictField: string;
  conflictStatus: string;
  conflictCandidates: string;
  sourceMapAvailable: string;
  sourceMapUnavailable: string;
  viewSourceDetails: string;
  hideSourceDetails: string;
  calculated: string;
  formula: string;
}

export default function DataQualityPanel({
  missingFields,
  conflicts,
  sourceMapAvailable,
  sourceMap,
  labels,
}: {
  missingFields: string[];
  conflicts: ConflictSummary[];
  sourceMapAvailable: boolean;
  sourceMap: Record<string, Record<string, unknown>> | null;
  labels: Labels;
}) {
  const [showSourceMap, setShowSourceMap] = useState(false);

  return (
    <div className="space-y-3">
      {/* Quick-scan summary strip */}
      <div className="flex flex-wrap gap-2">
        <SummaryChip
          ok={missingFields.length === 0}
          okText={labels.noMissingFields}
          badText={`${labels.missingFields}: ${missingFields.length}`}
        />
        <SummaryChip
          ok={conflicts.length === 0}
          okText={labels.noConflicts}
          badText={`${labels.conflicts}: ${conflicts.length}`}
        />
        <SummaryChip
          ok={sourceMapAvailable}
          okText={labels.sourceMapAvailable}
          badText={labels.sourceMapUnavailable}
        />
      </div>

      {/* Missing fields */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
          {labels.missingFields}
        </h3>
        {missingFields.length === 0 ? (
          <p className="text-sm text-emerald-600 dark:text-emerald-400">{labels.noMissingFields}</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {missingFields.map((field) => (
              <span
                key={field}
                className="text-xs font-mono px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-900"
              >
                {field}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Conflicts */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">{labels.conflicts}</h3>
        {conflicts.length === 0 ? (
          <p className="text-sm text-emerald-600 dark:text-emerald-400">{labels.noConflicts}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-400">
                <tr>
                  <th className="text-start font-medium py-1 pe-3">{labels.conflictField}</th>
                  <th className="text-start font-medium py-1 pe-3">{labels.conflictStatus}</th>
                  <th className="text-start font-medium py-1">{labels.conflictCandidates}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {conflicts.map((c) => (
                  <tr key={c.field_name}>
                    <td className="py-1.5 pe-3 font-mono text-rose-600 dark:text-rose-400">{c.field_name}</td>
                    <td className="py-1.5 pe-3 text-gray-600 dark:text-gray-400">{c.resolution_status}</td>
                    <td className="py-1.5 num text-gray-600 dark:text-gray-400">{c.candidate_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Source traceability */}
      <div>
        <div className="flex items-center gap-2">
          <span
            className={`status-dot ${sourceMapAvailable ? "status-dot-green" : "status-dot-gray"}`}
          />
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {sourceMapAvailable ? labels.sourceMapAvailable : labels.sourceMapUnavailable}
          </span>
          {sourceMapAvailable && sourceMap && (
            <button
              onClick={() => setShowSourceMap((v) => !v)}
              className="text-xs text-mejhr-600 dark:text-mejhr-400 hover:underline ms-2"
            >
              {showSourceMap ? labels.hideSourceDetails : labels.viewSourceDetails}
            </button>
          )}
        </div>

        {showSourceMap && sourceMap && (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs">
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {Object.entries(sourceMap).map(([field, info]) => (
                  <tr key={field}>
                    <td className="py-1.5 pe-3 font-mono text-gray-500 dark:text-gray-400 align-top whitespace-nowrap">
                      {field}
                    </td>
                    <td className="py-1.5 text-gray-700 dark:text-gray-300 align-top" dir="auto">
                      {info.calculated ? (
                        <span>
                          {labels.calculated}: <span className="font-mono">{String(info.formula ?? "")}</span>
                        </span>
                      ) : (
                        <span>{String(info.label_ar ?? "")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryChip({ ok, okText, badText }: { ok: boolean; okText: string; badText: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
        ok
          ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-900"
          : "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-900"
      }`}
    >
      <span className={`status-dot ${ok ? "status-dot-green" : "status-dot-yellow"}`} />
      {ok ? okText : badText}
    </span>
  );
}
