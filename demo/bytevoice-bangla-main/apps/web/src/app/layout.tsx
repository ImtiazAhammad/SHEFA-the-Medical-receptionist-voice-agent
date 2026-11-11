import type { Metadata, Viewport } from "next";
import { Hind_Siliguri, Inter } from "next/font/google";
import "./globals.css";

const banglaFont = Hind_Siliguri({
  variable: "--font-bangla",
  subsets: ["bengali", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const latinFont = Inter({
  variable: "--font-latin",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "ByteVoice Bangla: AI receptionist for clinics",
    template: "%s · ByteVoice Bangla",
  },
  description:
    "A Bangla-speaking AI receptionist that answers clinic calls 24 hours a day, books appointments and hands staff a clean record of every call.",
};

export const viewport: Viewport = {
  themeColor: "#05211f",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="bn" className={`${banglaFont.variable} ${latinFont.variable} h-full antialiased`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
