import type { Metadata } from "next";
import { RequireSignIn } from "@/components/RequireSignIn";
import { BookingFlow } from "./BookingFlow";

export const metadata: Metadata = { title: "Your booking" };

export default function BookPage() {
  return (
    <RequireSignIn role="guest">
      <BookingFlow />
    </RequireSignIn>
  );
}
