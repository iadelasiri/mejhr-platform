const ACCENT_COLORS = {
  default: "border-t-gray-300 dark:border-t-gray-700",
  balanceSheet: "border-t-blue-500 dark:border-t-blue-500",
  incomeStatement: "border-t-emerald-500 dark:border-t-emerald-500",
  cashFlow: "border-t-violet-500 dark:border-t-violet-500",
  price: "border-t-cyan-500 dark:border-t-cyan-500",
} as const;

export default function SectionCard({
  title,
  accent = "default",
  children,
}: {
  title: string;
  accent?: keyof typeof ACCENT_COLORS;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 border-t-2 ${ACCENT_COLORS[accent]} rounded-xl p-4`}
    >
      <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">{title}</h2>
      <div>{children}</div>
    </div>
  );
}
