import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "dipeen — AI Agent Workspace",
  description: "Multi-PM agent collaboration platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" data-dipeen-locale="ko" data-dipeen-theme="light">
      <body className="ds-page h-screen overflow-hidden">{children}</body>
    </html>
  );
}
