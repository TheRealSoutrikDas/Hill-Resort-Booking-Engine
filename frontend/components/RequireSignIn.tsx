"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { loginHref } from "@/lib/next-path";
import { useSession } from "./SessionProvider";

/**
 * Pages that need an account (booking, My bookings, the staff inbox). A signed-out
 * visitor is sent to log in and brought back here afterwards (D-24, A-158). The API
 * checks every request anyway; this only spares a page that would fail.
 */
type Props = { role?: "guest" | "staff"; children: React.ReactNode };

export function RequireSignIn(props: Props) {
  // Reading the address needs a Suspense boundary under cacheComponents.
  return (
    <Suspense fallback={<p className="page notice">Checking that you are signed in.</p>}>
      <Guard {...props} />
    </Suspense>
  );
}

function Guard({ role, children }: Props) {
  const { status, me } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const here = search.size ? `${pathname}?${search.toString()}` : pathname;

  useEffect(() => {
    if (status === "signed-out") router.replace(loginHref(here));
  }, [status, router, here]);

  if (status === "loading" || status === "signed-out") {
    return <p className="page notice">Checking that you are signed in.</p>;
  }
  if (status === "unavailable") {
    return (
      <p className="page notice" role="alert">
        We could not reach our booking system. Refresh the page to try again.
      </p>
    );
  }
  if (role && me?.role !== role) {
    return (
      <div className="page notice">
        <p>
          {role === "guest"
            ? "Staff accounts cannot make bookings. Log out and use a guest account."
            : "This page is for CompanyA staff."}
        </p>
        <p>
          <Link href="/">Go to the home page</Link>
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
