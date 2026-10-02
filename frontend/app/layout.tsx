import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NarraX — Narrative Intelligence",
  description: "Real-Time Narrative Intelligence Engine",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
