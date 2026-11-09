"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./staff.module.css";

const SECTIONS = [
  { href: "/staff/inbox", label: "Inbox" },
  { href: "/staff/alerts", label: "GM alerts" },
  { href: "/staff/metrics", label: "Metrics" },
];

export function StaffNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Staff" className={`page ${styles.subnav}`}>
      {SECTIONS.map((s) => (
        <Link
          key={s.href}
          href={s.href}
          aria-current={pathname === s.href || (s.href === "/staff/inbox" && pathname.startsWith("/staff/enquiries")) ? "page" : undefined}
        >
          {s.label}
        </Link>
      ))}
    </nav>
  );
}
