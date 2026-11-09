import type { Metadata } from "next";
import { RequireSignIn } from "@/components/RequireSignIn";
import { StaffNav } from "./StaffNav";
import styles from "./staff.module.css";

export const metadata: Metadata = { title: { default: "Staff", template: "%s | Staff | CompanyA" } };

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireSignIn role="staff">
      <StaffNav />
      <div className={`page ${styles.wrap}`}>{children}</div>
    </RequireSignIn>
  );
}
