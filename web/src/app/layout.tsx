import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "develop_assistant",
  description: "develop_assistant Web アプリケーション",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
