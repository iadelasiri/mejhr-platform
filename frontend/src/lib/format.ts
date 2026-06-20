/**
 * Display-only formatting helpers. These never compute ratios or derived
 * financial metrics — they only parse a Decimal-as-string value from the
 * API and render it with thousand separators.
 *
 * Numerals are always rendered as English digits (0-9), even on the
 * Arabic-locale UI — Arabic labels, English numerals, by explicit
 * requirement. The `locale` parameter is kept on these signatures only
 * for the caller-provided "not available" text and is intentionally NOT
 * used to select a numbering system (no "ar-SA" Intl calls here — those
 * default to Arabic-Indic digits, which is exactly what must be avoided).
 */

export interface FormattedNumber {
  text: string;
  isNegative: boolean;
  isAvailable: boolean;
}

/**
 * Parse a Decimal-as-string field from the financials API (e.g.
 * "6200549000.0000") into a finite number, or null if missing/unparseable.
 * Never throws.
 */
export function parseFinancialNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Format a Decimal-as-string financial value for display with English
 * thousand separators and English digits (e.g. "168,320,000",
 * "-52,446,000"). Returns the locale's "not available" text when the
 * value is null/missing — never fabricates a placeholder number like 0.
 */
export function formatFinancialValue(
  value: string | number | null | undefined,
  _locale: string,
  notAvailableText: string,
): FormattedNumber {
  const n = parseFinancialNumber(value);
  if (n === null) {
    return { text: notAvailableText, isNegative: false, isAvailable: false };
  }
  const formatted = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n);
  return { text: formatted, isNegative: n < 0, isAvailable: true };
}

/**
 * Format a price/percentage Decimal-as-string value (e.g. close,
 * change_amount, change_pct) with English digits and 2 decimal places —
 * unlike formatFinancialValue (0 decimals, for large balance-sheet
 * figures), prices and percentages need fractional precision (e.g.
 * "34.30", "-1.15") to not be misleading when rounded to whole numbers.
 */
export function formatPriceValue(
  value: string | number | null | undefined,
  notAvailableText: string,
): FormattedNumber {
  const n = parseFinancialNumber(value);
  if (n === null) {
    return { text: notAvailableText, isNegative: false, isAvailable: false };
  }
  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
  return { text: formatted, isNegative: n < 0, isAvailable: true };
}

/** Format an integer count (e.g. reporting_scale) with English digits. */
export function formatInteger(
  value: number | null | undefined,
  _locale: string,
  notAvailableText: string,
): FormattedNumber {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return { text: notAvailableText, isNegative: false, isAvailable: false };
  }
  const formatted = new Intl.NumberFormat("en-US").format(value);
  return { text: formatted, isNegative: value < 0, isAvailable: true };
}

/**
 * Format an ISO timestamp for display. Locale still selects the textual
 * parts (e.g. Arabic month names on the Arabic UI), but `numberingSystem:
 * "latn"` forces day/year digits to remain English in both locales.
 */
export function formatDateTime(value: string | null | undefined, locale: string, notAvailableText: string): string {
  if (!value) return notAvailableText;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA" : "en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    numberingSystem: "latn",
  }).format(d);
}
