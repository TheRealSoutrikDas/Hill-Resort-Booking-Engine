import type { Metadata } from "next";
import { RequireSignIn } from "@/components/RequireSignIn";
import { AdminGate } from "./AdminGate";
import styles from "./admin.module.css";

export const metadata: Metadata = { title: { default: "Admin", template: "%s | Admin | CompanyA" } };

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireSignIn role="staff">
      <AdminGate>
        <div className={`page ${styles.wrap}`}>{children}</div>
      </AdminGate>
    </RequireSignIn>
  );
}
