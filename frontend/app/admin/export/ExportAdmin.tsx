"use client";

import { useState } from "react";
import { todayInIndia } from "@/lib/stay";
import styles from "../admin.module.css";

/**
 * A-185: a plain same-site link, so the session cookie goes with it and the browser
 * saves the file the backend names. The backend checks access; the file has one row
 * per booking line (D-30).
 */
export function ExportAdmin() {
  const [date, setDate] = useState(() => todayInIndia());
  return (
    <>
      <h1>Daily export</h1>
      <p className="muted">
        The bookings confirmed or cancelled on one day (India time), for the reservation system. One row per room line.
        The same day always gives the same file.
      </p>
      <div className={styles.toolbar}>
        <label>
          Day
          <input type="date" value={date} required onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
        <a className="button" href={`/api/exports/bookings.csv?date=${date}`} download>
          Download bookings-{date}.csv
        </a>
      </div>
    </>
  );
}
