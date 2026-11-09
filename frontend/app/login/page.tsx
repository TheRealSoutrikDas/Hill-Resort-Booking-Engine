import type { Metadata } from "next";
import { Suspense } from "react";
import styles from "../auth.module.css";
import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <div className={`page ${styles.wrap}`}>
      <h1>Log in</h1>
      <p className="muted">Log in to book rooms and see your bookings.</p>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
