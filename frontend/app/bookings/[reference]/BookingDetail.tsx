"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { PriceBreakdown } from "@/components/PriceBreakdown";
import { api } from "@/lib/api";
import { paymentLabel } from "@/lib/booking-status";
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
      {cancelled && (
        <p className={styles.cancelNote} role="status">
          Cancelled. A full refund is in progress.
        </p>
      )}
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
          {!cancelled && <CancelBooking booking={booking} onCancelled={setBooking} />}
          <p>
            <Link href="/my-bookings">My bookings</Link> or <Link href="/rooms">book another stay</Link>
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

/**
 * A-174: cancelling happens here, where the guest sees what is being cancelled, and
 * needs a second click on the page (no browser pop-up). The backend decides whether it
 * is still allowed (until the day before check-in, A-51).
 */
function CancelBooking({ booking, onCancelled }: { booking: BookingOut; onCancelled: (b: BookingOut) => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (!booking.can_cancel) {
    return (
      <section className={styles.panel} aria-labelledby="change-title">
        <h2 id="change-title">Changes</h2>
        <p>Online cancellation closes the day before check-in. To change or cancel now, please contact the resort.</p>
      </section>
    );
  }

  async function cancel() {
    setBusy(true);
    setProblem(null);
    try {
      onCancelled(await api<BookingOut>(`/api/bookings/${encodeURIComponent(booking.reference)}/cancel`, { method: "POST" }));
    } catch (error) {
      setBusy(false);
      setProblem(error instanceof ApiError ? error.message : "The booking could not be cancelled. Please try again.");
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="cancel-title">
      <h2 id="cancel-title">Cancel</h2>
      <p>You can cancel online until the day before check-in, with a full refund.</p>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      {asking ? (
        <div className={styles.confirm}>
          <p>
            <strong>Cancel booking {booking.reference}?</strong> The rooms go back on sale.
          </p>
          <div className={styles.confirmActions}>
            <button type="button" className="button" disabled={busy} onClick={cancel}>
              {busy ? "Cancelling" : "Yes, cancel it"}
            </button>
            <button type="button" className="button-quiet" disabled={busy} onClick={() => setAsking(false)}>
              Keep my booking
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="button-quiet" onClick={() => setAsking(true)}>
          Cancel this booking
        </button>
      )}
    </section>
  );
}
