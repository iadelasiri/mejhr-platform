import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mejhr — Saudi Financial Data Platform",
  description:
    "Professional Saudi stock screener and financial data platform. Official data from Saudi Exchange.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
