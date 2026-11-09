import Link from "next/link";
import styles from "./SiteFooter.module.css";

export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className="page">
        <p>CompanyA, a coffee-estate resort in Chikkamagaluru, Karnataka.</p>
        <p>
          <Link href="/privacy">How we use your details</Link>
        </p>
        <p className={styles.demo}>
          This is a demonstration site. Payments, emails and messages are simulated; no money is
          taken and nothing is sent.
        </p>
      </div>
    </footer>
  );
}
