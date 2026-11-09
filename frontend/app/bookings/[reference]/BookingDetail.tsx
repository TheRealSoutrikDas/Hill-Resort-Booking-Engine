"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { PriceBreakdown } from "@/components/PriceBreakdown";
import { api } from "@/lib/api";
import { lineLabel, loadNames, type Names } from "@/lib/catalogue";
import { ApiError } from "@/lib/errors";
import { stayLabel } from "@/lib/stay";
import type { BookingOut } from "@/lib/types";
import styles from "../../book/[holdId]/book.module.css";

export function BookingDetail() {
  const { reference } = useParams<{ reference: string }>();
  const [booking, setBooking] = useState<BookingOut | null>(null);
  const [names, setNames] = useState<Names | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    api<BookingOut>(`/api/bookings/${encodeURIComponent(reference)}`)
      .then((b) => current && setBooking(b))
      .catch((error: unknown) => {
        if (current)
          setProblem(
            error instanceof ApiError && error.status === 404
              ? "We could not find this booking in your account."
              : "This booking could not be loaded. Refresh the page to try again.",
          );
      });
    loadNames()
      .then((n) => current && setNames(n))
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [reference]);

  if (problem) {
    return (
      <div className={`page ${styles.wrap}`}>
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      </div>
    );
  }
  if (!booking) return <p className="page notice">Loading your booking.</p>;

  const cancelled = booking.status === "cancelled";
  return (
    <div className={`page ${styles.wrap}`}>
      <h1>{cancelled ? "Booking cancelled" : "Your booking is confirmed"}</h1>
      <div className={styles.layout}>
        <div className={styles.steps}>
          <section className={styles.panel} aria-labelledby="reference-title">
            <h2 id="reference-title">Booking reference</h2>
            <p className={styles.reference}>{booking.reference}</p>
            <p className="muted">
              Quote this reference if you contact us.{" "}
              {!cancelled && `A confirmation would be emailed to ${booking.guest.email} (emails are simulated in this demo).`}
            </p>
          </section>
          <section className={styles.panel} aria-labelledby="guest-title">
            <h2 id="guest-title">Guest</h2>
            <p className={styles.guest}>
              {booking.guest.name}
              <br />
              {booking.guest.email}
              <br />
              {booking.guest.phone}
            </p>
          </section>
          <section className={styles.panel} aria-labelledby="payment-title">
            <h2 id="payment-title">Payment</h2>
            <p>
              {paymentLabel(booking.payment_status)}
              {booking.payment_reference && <span className="muted"> (reference {booking.payment_reference})</span>}
            </p>
          </section>
          <p>
            <Link href="/rooms">Book another stay</Link>
          </p>
        </div>
        <aside className={styles.panel} aria-labelledby="stay-title">
          <h2 id="stay-title">Your stay</h2>
          <p className={styles.stay}>{stayLabel(booking.check_in, booking.check_out)}</p>
          <ul className={styles.lines}>
            {booking.price.lines.map((l) => (
              <li key={`${l.room_type}.${l.rate_plan}`}>{lineLabel(names, l)}</li>
            ))}
          </ul>
          <PriceBreakdown price={booking.price} />
        </aside>
      </div>
    </div>
  );
}

function paymentLabel(status: string): string {
  switch (status) {
    case "succeeded":
      return "Paid in full";
    case "refunded":
      return "Refunded in full";
    case "refund_pending":
      return "Refund in progress";
    default:
      return status.replaceAll("_", " ");
  }
}
