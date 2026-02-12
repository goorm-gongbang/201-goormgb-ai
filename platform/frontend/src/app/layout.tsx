import type { Metadata } from "next";
import { Suspense } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import SecurityLayer from "@/components/security/SecurityLayer";
import SecurityTrigger from "@/components/security/SecurityTrigger";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Traffic-Master | 티켓 예매",
  description: "Traffic-Master 경기 티켓 예매 시스템",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
        {/* Stage 3: Global Security Challenge Interceptor */}
        <SecurityLayer />
        <Suspense fallback={null}>
          <SecurityTrigger />
        </Suspense>
      </body>
    </html>
  );
}

