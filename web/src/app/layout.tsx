import type { Metadata } from "next";
import { Geist, Geist_Mono, Spectral } from "next/font/google";

import { ThemeProvider } from "@/components/theme";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
/** Display serif for page titles, as on Spectrum UI. */
const spectral = Spectral({ variable: "--font-spectral", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: { default: "OpenGRC", template: "%s · OpenGRC" },
  description: "Run a security program on an open object model.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${spectral.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <ThemeProvider>
          <TooltipProvider>{children}</TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
