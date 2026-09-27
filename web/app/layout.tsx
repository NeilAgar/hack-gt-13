import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "StaffTrace",
  description:
    "Staffing consistency for Georgia nursing homes, based on public CMS Payroll-Based Journal data.",
};

// The Grok voice line is served by the API (api/voice.py), next to /api.
const VOICE_URL = `${(process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api").replace(/\/api\/?$/, "")}/voice`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#content">
          Skip to content
        </a>
        <header className="site-header">
          <div className="header-inner">
            <div>
              <p className="eyebrow">Georgia nursing homes</p>
              <p className="wordmark">
                <a href="/">StaffTrace</a>
              </p>
            </div>
            <nav className="nav" aria-label="Primary">
              <a href={VOICE_URL}>Ask Grok</a>
            </nav>
          </div>
        </header>
        <main id="content">{children}</main>
        <footer className="site-footer">
          <div className="footer-inner">
            <p>PBJ staffing data is self-reported.</p>
            <p>
              {"Chen & Dillender (NBER w34037) and Gandhi, Olenski & Shi (NBER w34491)."}
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
