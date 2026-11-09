"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { canAdmin, useSession } from "@/components/SessionProvider";
import styles from "./admin.module.css";

const SECTIONS = [
  { href: "/admin/inventory", label: "Inventory" },
  { href: "/admin/promos", label: "Promo codes" },
  { href: "/admin/export", label: "Daily export" },
];

/** The events team is signed in as staff but has no admin access (A-180). */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const { me } = useSession();
  const pathname = usePathname();
  if (!canAdmin(me)) {
    return (
      <div className="page notice">
        <h1>Admin</h1>
        <p>Admin is for the reservations team and the GM.</p>
        <p>
          <Link href="/">Go to the home page</Link>
        </p>
      </div>
    );
  }
  return (
    <>
      <nav aria-label="Admin" className={`page ${styles.subnav}`}>
        {SECTIONS.map((s) => (
          <Link key={s.href} href={s.href} aria-current={pathname === s.href ? "page" : undefined}>
            {s.label}
          </Link>
        ))}
      </nav>
      {children}
    </>
  );
}
