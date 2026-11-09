import type { Metadata } from "next";
import { PhotoPanel } from "@/components/PhotoPanel";
import { PANEL_ENQUIRE } from "@/lib/photos";
import { FindBooking } from "./FindBooking";

export const metadata: Metadata = { title: "Find a booking" };

export default function FindBookingPage() {
  return (
    <PhotoPanel photo={PANEL_ENQUIRE}>
      <h1>Find a booking</h1>
      <p className="muted">Enter the booking reference and the guest&apos;s email to see the booking.</p>
      <FindBooking />
    </PhotoPanel>
  );
}
