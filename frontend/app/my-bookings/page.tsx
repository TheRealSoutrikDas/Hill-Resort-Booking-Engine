import type { Metadata } from "next";
import { RequireSignIn } from "@/components/RequireSignIn";
import { MyBookings } from "./MyBookings";

export const metadata: Metadata = { title: "My bookings" };

export default function MyBookingsPage() {
  return (
    <RequireSignIn role="guest">
      <MyBookings />
    </RequireSignIn>
  );
}
