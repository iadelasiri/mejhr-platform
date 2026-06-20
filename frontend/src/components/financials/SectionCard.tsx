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
  id,
  children,
}: {
  title: string;
  accent?: keyof typeof ACCENT_COLORS;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      id={id}
      className={`scroll-mt-28 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 border-t-2 ${ACCENT_COLORS[accent]} rounded-xl p-3.5`}
    >
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 pb-1.5 mb-1 border-b border-gray-100 dark:border-gray-800">
        {title}
      </h2>
      <div>{children}</div>
    </div>
  );
}
