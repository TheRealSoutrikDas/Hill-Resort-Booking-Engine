import type { Metadata } from "next";
import { RequireSignIn } from "@/components/RequireSignIn";
import { BookingDetail } from "./BookingDetail";

export const metadata: Metadata = { title: "Booking" };

export default function BookingPage() {
  return (
    <RequireSignIn>
      <BookingDetail />
    </RequireSignIn>
  );
}
