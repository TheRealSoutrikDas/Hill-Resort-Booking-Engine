"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Field, FormAlert, PasswordField, formStyles } from "@/components/forms/Field";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { ApiError, UNREACHABLE, waitMessage } from "@/lib/errors";
import { safeNextPath, signupHref } from "@/lib/next-path";
import type { Me } from "@/lib/types";

export function LoginForm() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const { signedIn } = useSession();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setProblem(null);
    try {
      const me = await api<Me>("/api/auth/login", {
        method: "POST",
        body: { email: String(form.get("email") ?? ""), password: String(form.get("password") ?? "") },
      });
      signedIn(me);
      router.replace(next); // A-163: staff go to `next` or home until the inbox exists
    } catch (error) {
      setProblem(describe(error));
      setBusy(false);
    }
  }

  return (
    <form className={formStyles.form} onSubmit={submit} noValidate={false}>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      <Field label="Email" name="email" type="email" autoComplete="email" required maxLength={320} />
      <PasswordField label="Password" name="password" autoComplete="current-password" required maxLength={128} />
      <div className={formStyles.actions}>
        <button type="submit" className="button" disabled={busy}>
          {busy ? "Logging in" : "Log in"}
        </button>
      </div>
      <p>
        New to CompanyA? <Link href={signupHref(next)}>Create an account</Link>
      </p>
      <p className="muted">Forgot your password? Contact the resort and we will help you.</p>
    </form>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "invalid_credentials") return "Email or password is incorrect.";
    if (error.code === "rate_limited") return waitMessage(error);
    if (error.code === UNREACHABLE) return error.message;
    return error.message;
  }
  return "Something went wrong. Please try again.";
}
