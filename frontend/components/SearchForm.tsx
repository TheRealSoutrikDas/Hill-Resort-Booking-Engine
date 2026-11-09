"use client";

import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { HORIZON_DAYS, MAX_GUESTS, addDays, datesProblem, searchQuery, todayInIndia, type Search } from "@/lib/stay";
import styles from "./SearchForm.module.css";

/** Dates and guests. Submitting opens /rooms with the search in the address. */
// "Today" must come from the visitor's clock when the page runs, not from the moment the
// page was built (the home page is pre-rendered). On the server it is unknown (null).
const noSubscription = () => () => {};
function useToday(): string | null {
  return useSyncExternalStore(noSubscription, () => todayInIndia(), () => null);
}

export function SearchForm({ initial, compact = false }: { initial?: Search; compact?: boolean }) {
  const router = useRouter();
  const today = useToday();
  const [checkIn, setCheckIn] = useState(initial?.checkIn ?? "");
  const [checkOut, setCheckOut] = useState(initial?.checkOut ?? "");
  const [guests, setGuests] = useState(initial?.guests ?? 2);
  const [problem, setProblem] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!checkIn || !checkOut) {
      setProblem("Choose your check-in and check-out dates.");
      return;
    }
    const found = datesProblem(checkIn, checkOut, today ?? todayInIndia());
    setProblem(found);
    if (found) return;
    router.push(`/rooms?${searchQuery({ checkIn, checkOut, guests })}`);
  }

  return (
    <form className={`${styles.form} ${compact ? styles.compact : ""}`} onSubmit={submit} aria-label="Search rooms">
      <label className={styles.field}>
        <span>Check-in</span>
        <input
          type="date"
          value={checkIn}
          min={today ?? undefined}
          max={today ? addDays(today, HORIZON_DAYS) : undefined}
          onChange={(e) => {
            setCheckIn(e.target.value);
            if (e.target.value && (!checkOut || checkOut <= e.target.value)) setCheckOut(addDays(e.target.value, 1));
          }}
          required
        />
      </label>
      <label className={styles.field}>
        <span>Check-out</span>
        <input
          type="date"
          value={checkOut}
          min={checkIn ? addDays(checkIn, 1) : today ? addDays(today, 1) : undefined}
          max={today ? addDays(today, HORIZON_DAYS + 14) : undefined}
          onChange={(e) => setCheckOut(e.target.value)}
          required
        />
      </label>
      <label className={styles.field}>
        <span>Guests</span>
        <input
          type="number"
          min={1}
          max={MAX_GUESTS}
          value={guests}
          onChange={(e) => setGuests(Math.max(1, Math.min(MAX_GUESTS, Number(e.target.value) || 1)))}
          required
        />
      </label>
      <button type="submit" className={`button ${styles.submit}`}>
        Check availability
      </button>
      {problem && (
        <p className={styles.problem} role="alert">
          {problem}
        </p>
      )}
    </form>
  );
}
