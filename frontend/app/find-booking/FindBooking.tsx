"use client";

import Link from "next/link";
import { useState } from "react";
import { Field, FormAlert, formStyles } from "@/components/forms/Field";
import { api } from "@/lib/api";
import { linesLabel, paymentLabel } from "@/lib/booking-status";
import { ApiError, waitMessage } from "@/lib/errors";
import { formatInr } from "@/lib/format";
import { loginHref } from "@/lib/next-path";
import { stayLabel } from "@/lib/stay";
import type { LookupOut } from "@/lib/types";
import styles from "./find.module.css";

/** View only (A-48): cancelling needs signing in as the account that booked. */
export function FindBooking() {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [found, setFound] = useState<LookupOut | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setProblem(null);
    setFound(null);
    try {
      setFound(
        await api<LookupOut>("/api/bookings/lookup", {
          method: "POST",
          body: {
            reference: String(form.get("reference") ?? "").trim().toUpperCase(),
            email: String(form.get("email") ?? "").trim(),
          },
        }),
      );
    } catch (error) {
      if (error instanceof ApiError && error.code === "rate_limited") setProblem(waitMessage(error));
      else if (error instanceof ApiError && error.status === 404) setProblem(error.message); // one message for either mistake
      else setProblem(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className={formStyles.form} onSubmit={submit}>
        {problem && (
          <FormAlert>
            <p>{problem}</p>
          </FormAlert>
        )}
        <Field label="Booking reference" name="reference" required maxLength={32} placeholder="BK-XXXXXXXX" autoComplete="off" />
        <Field label="Email" name="email" type="email" required maxLength={320} autoComplete="email" />
        <div className={formStyles.actions}>
          <button type="submit" className="button" disabled={busy}>
            {busy ? "Looking" : "Find booking"}
          </button>
        </div>
      </form>

      {found && (
        <section className={styles.result} aria-labelledby="found-title">
          <h2 id="found-title">
            {found.reference}
            {found.status === "cancelled" ? ", cancelled" : ""}
          </h2>
          <p className={styles.dates}>{stayLabel(found.check_in, found.check_out)}</p>
          <ul className={styles.lines}>
            {linesLabel(found.lines).map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
          <dl className={styles.facts}>
            <div>
              <dt>Guest</dt>
              <dd>
                {found.guest_name} ({found.guest_email_masked})
              </dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd>{formatInr(found.total_paise)}, GST included</dd>
            </div>
            <div>
              <dt>Payment</dt>
              <dd>{paymentLabel(found.payment_status)}</dd>
            </div>
          </dl>
          {found.status !== "cancelled" && (
            <p className="muted">
              To cancel, <Link href={loginHref(`/bookings/${found.reference}`)}>log in</Link> with the account that made the
              booking.
            </p>
          )}
        </section>
      )}
    </>
  );
}
