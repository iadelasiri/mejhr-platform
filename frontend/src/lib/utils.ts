import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(
  value: number | string | null | undefined,
  options?: Intl.NumberFormatOptions
): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  return new Intl.NumberFormat("en-US", options).format(num);
}

export function formatCurrency(value: number | string | null | undefined, currency = "SAR"): string {
  return formatNumber(value, {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
    notation: "compact",
    compactDisplay: "short",
  });
}

export function formatPercent(value: number | string | null | undefined, decimals = 1): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  return `${(num * 100).toFixed(decimals)}%`;
}

export function formatMultiple(value: number | string | null | undefined, decimals = 1): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  return `${num.toFixed(decimals)}x`;
}

export function dataQualityColor(status: string | null | undefined): string {
  switch (status) {
    case "complete": return "text-green-600 dark:text-green-400";
    case "partial": return "text-yellow-600 dark:text-yellow-400";
    case "missing_financials": return "text-orange-600 dark:text-orange-400";
    case "missing_price": return "text-orange-600 dark:text-orange-400";
    case "poor": return "text-red-600 dark:text-red-400";
    case "sample_not_official": return "text-purple-600 dark:text-purple-400";
    default: return "text-gray-400 dark:text-gray-600";
  }
}
