"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { loginHref } from "@/lib/next-path";
import { canAdmin, useSession } from "./SessionProvider";
import styles from "./AccountMenu.module.css";

export function AccountMenu() {
  const { status, me, logOut } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);

  if (status === "loading") return <span className={styles.placeholder} aria-hidden="true" />;

  if (status === "signed-in" && me) {
    const firstName = me.full_name.split(" ")[0] || me.full_name;
    return (
      <div className={styles.menu}>
        {me.role === "guest" && <Link href="/my-bookings">My bookings</Link>}
        {me.role === "staff" && <Link href="/staff/inbox">Staff</Link>}
        {canAdmin(me) && <Link href="/admin/inventory">Admin</Link>}
        <span className={styles.name} title={me.email}>
          {firstName}
        </span>
        <button
          type="button"
          className={styles.link}
          disabled={leaving}
          onClick={async () => {
            setLeaving(true);
            await logOut().catch(() => undefined);
            setLeaving(false);
            router.push("/");
          }}
        >
          {leaving ? "Logging out" : "Log out"}
        </button>
      </div>
    );
  }

  const next = pathname === "/login" || pathname === "/signup" ? "/" : pathname;
  return (
    <Link href={loginHref(next)} className={styles.login}>
      Log in
    </Link>
  );
}
