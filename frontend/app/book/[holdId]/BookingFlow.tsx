"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Field, FormAlert, formStyles } from "@/components/forms/Field";
import { PriceBreakdown } from "@/components/PriceBreakdown";
import { api } from "@/lib/api";
import { lineLabel, loadNames, type Names } from "@/lib/catalogue";
import { ApiError } from "@/lib/errors";
import { formatInr } from "@/lib/format";
import { forgetPaymentKey, paymentKey } from "@/lib/payment-key";
import { searchQuery, stayLabel } from "@/lib/stay";
import type { GuestDetails, HoldOut, PaymentOut } from "@/lib/types";
import styles from "./book.module.css";

type Outcome = "success" | "decline" | "timeout";

export function BookingFlow() {
  const { holdId } = useParams<{ holdId: string }>();
  const router = useRouter();
  const [hold, setHold] = useState<HoldOut | null>(null);
  const [names, setNames] = useState<Names | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let current = true;
    api<HoldOut>(`/api/holds/${encodeURIComponent(holdId)}`)
      .then((h) => {
        if (!current) return;
        if (h.status === "converted" && h.booking_reference) router.replace(`/bookings/${h.booking_reference}`);
        else setHold(h);
      })
      .catch((error: unknown) => {
        if (current)
          setLoadError(
            error instanceof ApiError && error.status === 404
              ? "We could not find this booking. It may belong to another account."
              : "This booking could not be loaded. Refresh the page to try again.",
          );
      });
    loadNames()
      .then((n) => current && setNames(n))
      .catch(() => undefined); // codes are shown instead of names
    return () => {
      current = false;
    };
  }, [holdId, router]);

  // The countdown is for display only; the server decides expiry (A-167).
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  if (loadError) {
    return (
      <div className={`page ${styles.wrap}`}>
        <FormAlert>
          <p>{loadError}</p>
        </FormAlert>
      </div>
    );
  }
  if (!hold) return <p className="page notice">Loading your booking.</p>;

  const lines = hold.price.lines;
  const again = `/rooms?${searchQuery(
    { checkIn: hold.check_in, checkOut: hold.check_out, guests: lines.reduce((n, l) => n + l.guests, 0) },
    lines.map((l) => ({ roomType: l.room_type, ratePlan: l.rate_plan, units: l.units, guests: l.guests })),
  )}`;
  const secondsLeft = Math.max(0, Math.floor((Date.parse(hold.expires_at) - now) / 1000));
  const expired = hold.status === "expired" || hold.status === "released" || secondsLeft === 0;

  return (
    <div className={`page ${styles.wrap}`}>
      <h1>Your booking</h1>
      <div className={styles.layout}>
        <div className={styles.steps}>
          {expired ? (
            <section className={styles.panel} aria-labelledby="expired-title">
              <h2 id="expired-title">
                {hold.status === "released" ? "You cancelled this booking" : "Your 10 minutes are up"}
              </h2>
              <p>
                {hold.status === "released"
                  ? "The rooms have been released."
                  : "We released the rooms so others can book them. They may still be free."}
              </p>
              <Link className="button" href={again}>
                Check these rooms again
              </Link>
            </section>
          ) : (
            <>
              <p className={styles.timer} role="timer" aria-live="off">
                Rooms held for you for {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
              </p>
              <GuestStep hold={hold} onSaved={setHold} />
              {hold.guest && <PaymentStep hold={hold} onExpired={() => setHold({ ...hold, status: "expired" })} />}
              <CancelHold holdId={hold.id} again={again} onReleased={() => setHold({ ...hold, status: "released" })} />
            </>
          )}
        </div>
        <aside className={styles.panel} aria-labelledby="stay-title">
          <h2 id="stay-title">Your stay</h2>
          <p className={styles.stay}>{stayLabel(hold.check_in, hold.check_out)}</p>
          <ul className={styles.lines}>
            {lines.map((l) => (
              <li key={`${l.room_type}.${l.rate_plan}`}>{lineLabel(names, l)}</li>
            ))}
          </ul>
          <PriceBreakdown price={hold.price} />
        </aside>
      </div>
    </div>
  );
}

const GUEST_FIELD: Record<string, keyof GuestDetails> = {
  invalid_guest_name: "name",
  invalid_guest_email: "email",
  invalid_guest_phone: "phone",
};

function GuestStep({ hold, onSaved }: { hold: HoldOut; onSaved: (h: HoldOut) => void }) {
  const [editing, setEditing] = useState(!hold.guest);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof GuestDetails, string>>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const initial = hold.guest ?? hold.guest_suggestion;

  if (!editing && hold.guest) {
    return (
      <section className={styles.panel} aria-labelledby="guest-title">
        <h2 id="guest-title">Guest</h2>
        <p className={styles.guest}>
          {hold.guest.name}
          <br />
          {hold.guest.email}
          <br />
          {hold.guest.phone}
        </p>
        <button type="button" className="button-quiet" onClick={() => setEditing(true)}>
          Change guest details
        </button>
      </section>
    );
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      name: String(form.get("name") ?? "").trim(),
      email: String(form.get("email") ?? "").trim(),
      phone: String(form.get("phone") ?? "").trim(),
    };
    setBusy(true);
    setErrors({});
    setProblem(null);
    try {
      const updated = await api<HoldOut>(`/api/holds/${hold.id}/guest`, { method: "PUT", body });
      onSaved(updated);
      setEditing(false);
    } catch (error) {
      if (error instanceof ApiError && GUEST_FIELD[error.code]) setErrors({ [GUEST_FIELD[error.code]]: error.message });
      else setProblem(error instanceof ApiError ? error.message : "The details could not be saved. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="guest-title">
      <h2 id="guest-title">Who is staying</h2>
      <p className="muted">The guest who will check in. We use these details only for this booking.</p>
      <form className={formStyles.form} onSubmit={save}>
        {problem && (
          <FormAlert>
            <p>{problem}</p>
          </FormAlert>
        )}
        <Field label="Guest name" name="name" autoComplete="name" required maxLength={200} defaultValue={initial?.name ?? ""} error={errors.name} />
        <Field label="Guest email" name="email" type="email" autoComplete="email" required maxLength={320} defaultValue={initial?.email ?? ""} error={errors.email} />
        <Field label="Guest phone" name="phone" type="tel" autoComplete="tel" required maxLength={40} defaultValue={initial?.phone ?? ""} error={errors.phone} />
        <div className={formStyles.actions}>
          <button type="submit" className="button" disabled={busy}>
            {busy ? "Saving" : "Save guest details"}
          </button>
        </div>
      </form>
    </section>
  );
}

type PayState =
  | { kind: "ready" }
  | { kind: "paying" }
  | { kind: "declined" }
  | { kind: "timed-out" }
  | { kind: "processing" }
  | { kind: "refunded"; message: string }
  | { kind: "error"; message: string };

function PaymentStep({ hold, onExpired }: { hold: HoldOut; onExpired: () => void }) {
  const router = useRouter();
  const [outcome, setOutcome] = useState<Outcome>("success");
  const [state, setState] = useState<PayState>({ kind: "ready" });

  const pay = useCallback(
    async (simulate: Outcome) => {
      setState({ kind: "paying" });
      const key = paymentKey(hold.id); // the same key until this attempt has a final answer
      try {
        const result = await api<PaymentOut>(`/api/holds/${hold.id}/payment`, {
          method: "POST",
          body: { simulate },
          headers: { "Idempotency-Key": key },
        });
        switch (result.status) {
          case "confirmed":
            forgetPaymentKey(hold.id);
            router.push(`/bookings/${result.booking_reference}`);
            return;
          case "declined":
            forgetPaymentKey(hold.id);
            setState({ kind: "declined" });
            return;
          case "timed_out":
            // In this mock a timeout means "not charged" (A-62), so a new attempt is safe.
            forgetPaymentKey(hold.id);
            setState({ kind: "timed-out" });
            return;
          case "processing":
            setState({ kind: "processing" }); // keep the key: asking again returns the real answer
            return;
          default:
            forgetPaymentKey(hold.id);
            setState({
              kind: "refunded",
              message:
                result.failure ??
                "Your payment went through after the rooms were released, so it is being refunded in full.",
            });
        }
      } catch (error) {
        if (error instanceof ApiError && error.code === "hold_not_active") {
          forgetPaymentKey(hold.id);
          onExpired();
          return;
        }
        setState({ kind: "error", message: error instanceof ApiError ? error.message : "The payment could not be started. Please try again." });
      }
    },
    [hold.id, onExpired, router],
  );

  const busy = state.kind === "paying";
  return (
    <section className={styles.panel} aria-labelledby="pay-title">
      <h2 id="pay-title">Pay</h2>
      <fieldset className={styles.demo}>
        <legend>Demo payment outcome</legend>
        <p className="muted">
          This demonstration takes no real payments. Choose what the pretend payment provider does.
        </p>
        {(
          [
            ["success", "Payment succeeds"],
            ["decline", "Card is declined"],
            ["timeout", "Provider does not answer"],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className={formStyles.check}>
            <input type="radio" name="outcome" value={value} checked={outcome === value} onChange={() => setOutcome(value)} />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>

      <div aria-live="polite">
        {state.kind === "declined" && (
          <FormAlert>
            <p>The payment was declined and you were not charged. You can try again.</p>
          </FormAlert>
        )}
        {state.kind === "timed-out" && (
          <FormAlert>
            <p>The payment provider did not answer, so you were not charged. You can try again.</p>
          </FormAlert>
        )}
        {state.kind === "processing" && (
          <FormAlert>
            <p>Your payment is still being processed.</p>
            <p>
              <button type="button" className="button-quiet" onClick={() => pay(outcome)}>
                Check payment status
              </button>
            </p>
          </FormAlert>
        )}
        {state.kind === "refunded" && (
          <FormAlert>
            <p>{state.message}</p>
          </FormAlert>
        )}
        {state.kind === "error" && (
          <FormAlert>
            <p>{state.message}</p>
          </FormAlert>
        )}
      </div>

      {state.kind !== "refunded" && state.kind !== "processing" && (
        <button type="button" className={`button ${styles.pay}`} disabled={busy} onClick={() => pay(outcome)}>
          {busy ? "Paying" : `Pay ${formatInr(hold.price.total_paise)}`}
        </button>
      )}
    </section>
  );
}

function CancelHold({ holdId, again, onReleased }: { holdId: string; again: string; onReleased: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <p className={styles.cancel}>
      <button
        type="button"
        className={styles.link}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api<void>(`/api/holds/${holdId}`, { method: "DELETE" });
            onReleased();
          } catch {
            setBusy(false);
          }
        }}
      >
        {busy ? "Releasing the rooms" : "Cancel and release the rooms"}
      </button>{" "}
      or <Link href={again}>change rooms</Link>
    </p>
  );
}
