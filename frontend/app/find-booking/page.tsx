import type { Metadata } from "next";
import styles from "../auth.module.css";
import { FindBooking } from "./FindBooking";

export const metadata: Metadata = { title: "Find a booking" };

export default function FindBookingPage() {
  return (
    <div className={`page ${styles.wrap}`}>
      <h1>Find a booking</h1>
      <p className="muted">Enter the booking reference and the guest&apos;s email to see the booking.</p>
      <FindBooking />
    </div>
  );
}
