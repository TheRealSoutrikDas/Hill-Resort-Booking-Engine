"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { loginHref } from "@/lib/next-path";
import type { Line, Search } from "@/lib/stay";
import type { HoldOut } from "@/lib/types";
import styles from "./rooms.module.css";

type Props = {
  search: Search & { checkIn: string; checkOut: string };
  lines: Line[];
  promoCode: string | null;
  onPromoError: (message: string) => void;
};

/** Starts the booking: holds the rooms for 10 minutes, then opens the booking page. */
export function BookButton({ search, lines, promoCode, onPromoError }: Props) {
  const { status, me } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function book() {
    setProblem(null);
    if (status !== "signed-in") {
      // Sign-in is required to book (D-24). The choice is in the address, so `next`
      // brings the guest back to it (A-171).
      router.push(loginHref(`${pathname}${window.location.search}`));
      return;
    }
    setBusy(true);
    try {
      const hold = await api<HoldOut>("/api/holds", {
        method: "POST",
        body: {
          check_in: search.checkIn,
          check_out: search.checkOut,
          promo_code: promoCode,
          lines: lines.map((l) => ({ room_type: l.roomType, rate_plan: l.ratePlan, units: l.units, guests: l.guests })),
        },
      });
      router.push(`/book/${hold.id}`);
    } catch (error) {
      setBusy(false);
      if (!(error instanceof ApiError)) {
        setProblem("Something went wrong. Please try again.");
      } else if (error.code === "not_authenticated") {
        router.push(loginHref(`${pathname}${window.location.search}`));
      } else if (error.code === "not_available") {
        setProblem("Some of these rooms were booked a moment ago. Refresh the page to see what is left.");
      } else if (error.code === "invalid_promo_code" || error.code.startsWith("promo_")) {
        onPromoError(error.message);
      } else if (error.code === "forbidden") {
        setProblem("Staff accounts cannot make bookings. Log out and use a guest account.");
      } else {
        setProblem(error.message);
      }
    }
  }

  const isStaff = me?.role === "staff";
  return (
    <div className={styles.book}>
      <button type="button" className="button" onClick={book} disabled={busy || isStaff}>
        {busy ? "Holding your rooms" : status === "signed-in" ? "Book these rooms" : "Log in to book"}
      </button>
      {isStaff && <p className="muted">Staff accounts cannot make bookings.</p>}
      {!isStaff && (
        <p className="muted">
          We hold the rooms for 10 minutes while you add the guest&apos;s details and pay.
        </p>
      )}
      {problem && (
        <p className={styles.warn} role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}
