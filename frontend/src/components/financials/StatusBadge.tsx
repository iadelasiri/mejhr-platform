const STATUS_COLORS: Record<string, string> = {
  normalized: "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-900",
  partial: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-900",
  conflict: "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-900",
  pending: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700",
  failed: "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-900",
};

const STATUS_DOT: Record<string, string> = {
  normalized: "status-dot-green",
  partial: "status-dot-yellow",
  conflict: "status-dot-red",
  pending: "status-dot-gray",
  failed: "status-dot-red",
};

/** Reusable normalization_status indicator — same data, used in the header and filing card. */
export default function StatusBadge({ status, size = "md" }: { status: string; size?: "sm" | "md" }) {
  const colorClass = STATUS_COLORS[status] ?? STATUS_COLORS.pending;
  const dotClass = STATUS_DOT[status] ?? STATUS_DOT.pending;
  const sizeClass = size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-3 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium border ${sizeClass} ${colorClass}`}
    >
      <span className={`status-dot ${dotClass}`} />
      {status}
    </span>
  );
}
