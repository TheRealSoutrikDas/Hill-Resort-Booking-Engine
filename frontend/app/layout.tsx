import type { Metadata, Viewport } from "next";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CompanyA, Chikkamagaluru", template: "%s | CompanyA" },
  description: "Book rooms and villas directly at CompanyA, a coffee-estate resort in Chikkamagaluru, Karnataka.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#1f3b2d" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN">
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
