"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { api } from "@/lib/api";
import { linesLabel } from "@/lib/booking-status";
import { formatInr } from "@/lib/format";
import { stayLabel } from "@/lib/stay";
import type { MyBooking } from "@/lib/types";
import styles from "./my-bookings.module.css";

// The backend sorts bookings into these sections, in India's time zone, so the
// frontend does no date logic (D-37).
const TABS = [
  { section: "upcoming", label: "Upcoming", empty: "No upcoming stays." },
  { section: "current", label: "Current", empty: "You are not staying with us right now." },
  { section: "past", label: "Past", empty: "No past stays yet." },
  { section: "cancelled", label: "Cancelled", empty: "No cancelled bookings." },
] as const;
type Section = (typeof TABS)[number]["section"];

export function MyBookings() {
  const [bookings, setBookings] = useState<MyBooking[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Section | null>(null);

  useEffect(() => {
    let current = true;
    api<MyBooking[]>("/api/me/bookings")
      .then((b) => current && setBookings(b))
      .catch(() => current && setProblem("Your bookings could not be loaded. Refresh the page to try again."));
    return () => {
      current = false;
    };
  }, []);

  if (problem) {
    return (
      <div className={`page ${styles.wrap}`}>
        <h1>My bookings</h1>
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      </div>
    );
  }
  if (!bookings) return <p className="page notice">Loading your bookings.</p>;

  const count = (s: Section) => bookings.filter((b) => b.section === s).length;
  // A-173: open on Upcoming, or the first tab that has bookings.
  const active: Section = chosen ?? (count("upcoming") ? "upcoming" : (TABS.find((t) => count(t.section))?.section ?? "upcoming"));
  const shown = bookings.filter((b) => b.section === active);
  const tab = TABS.find((t) => t.section === active)!;

  return (
    <div className={`page ${styles.wrap}`}>
      <h1>My bookings</h1>
      {bookings.length === 0 ? (
        <div className={styles.empty}>
          <p>You have no bookings yet.</p>
          <Link className="button" href="/rooms">
            Find a room
          </Link>
        </div>
      ) : (
        <>
          <div className={styles.tabs} role="tablist" aria-label="Bookings by status">
            {TABS.map((t) => (
              <button
                key={t.section}
                type="button"
                role="tab"
                id={`tab-${t.section}`}
                aria-selected={t.section === active}
                aria-controls="booking-panel"
                className={styles.tab}
                onClick={() => setChosen(t.section)}
              >
                {t.label} <span className={styles.count}>{count(t.section)}</span>
              </button>
            ))}
          </div>
          <div id="booking-panel" role="tabpanel" aria-labelledby={`tab-${active}`}>
            {shown.length === 0 ? (
              <p className={styles.empty}>{tab.empty}</p>
            ) : (
              <ul className={styles.list}>
                {shown.map((b) => (
                  <li key={b.reference} className={styles.item}>
                    <div className={styles.head}>
                      <Link href={`/bookings/${b.reference}`} className={styles.reference}>
                        {b.reference}
                      </Link>
                      <span className={styles.total}>{formatInr(b.total_paise)}</span>
                    </div>
                    <p className={styles.dates}>{stayLabel(b.check_in, b.check_out)}</p>
                    <ul className={styles.lines}>
                      {linesLabel(b.lines).map((l) => (
                        <li key={l}>{l}</li>
                      ))}
                    </ul>
                    {b.status === "cancelled" && <p className={styles.cancelled}>Cancelled</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
