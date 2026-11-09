import type { Metadata } from "next";
import { Suspense } from "react";
import styles from "../auth.module.css";
import { SignupForm } from "./SignupForm";

export const metadata: Metadata = { title: "Create an account" };

export default function SignupPage() {
  return (
    <div className={`page ${styles.wrap}`}>
      <h1>Create an account</h1>
      <p className="muted">You need an account to book, so you can see and manage your bookings.</p>
      <Suspense fallback={null}>
        <SignupForm />
      </Suspense>
    </div>
  );
}
