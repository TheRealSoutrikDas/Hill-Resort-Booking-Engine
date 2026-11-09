import type { Metadata } from "next";
import { Suspense } from "react";
import { PhotoPanel } from "@/components/PhotoPanel";
import { PANEL_ACCOUNT } from "@/lib/photos";
import { SignupForm } from "./SignupForm";

export const metadata: Metadata = { title: "Create an account" };

export default function SignupPage() {
  return (
    <PhotoPanel photo={PANEL_ACCOUNT}>
      <h1>Create an account</h1>
      <p className="muted">You need an account to book, so you can see and manage your bookings.</p>
      <Suspense fallback={null}>
        <SignupForm />
      </Suspense>
    </PhotoPanel>
  );
}
