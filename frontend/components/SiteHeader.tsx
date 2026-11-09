import Link from "next/link";
import { Suspense } from "react";
import { AccountMenu } from "./AccountMenu";
import styles from "./SiteHeader.module.css";

export function SiteHeader() {
  return (
    <header className={styles.header}>
      <div className={`page ${styles.inner}`}>
        <Link href="/" className={styles.brand}>
          CompanyA
          <span className={styles.place}>Chikkamagaluru</span>
        </Link>
        <nav aria-label="Main" className={styles.navWrap}>
          <ul className={styles.nav}>
            <li>
              <Link href="/rooms">Rooms and villas</Link>
            </li>
            <li>
              <Link href="/#visit">Visit</Link>
            </li>
          </ul>
          <Suspense fallback={<span style={{ display: "inline-block", width: "4.5rem" }} />}>
            <AccountMenu />
          </Suspense>
        </nav>
      </div>
    </header>
  );
}
