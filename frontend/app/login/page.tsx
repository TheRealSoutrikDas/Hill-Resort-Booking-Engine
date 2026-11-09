import type { Metadata } from "next";
import { Suspense } from "react";
import { PhotoPanel } from "@/components/PhotoPanel";
import { PANEL_ACCOUNT } from "@/lib/photos";
import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <PhotoPanel photo={PANEL_ACCOUNT}>
      <h1>Log in</h1>
      <p className="muted">Log in to book rooms and see your bookings.</p>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </PhotoPanel>
  );
}
