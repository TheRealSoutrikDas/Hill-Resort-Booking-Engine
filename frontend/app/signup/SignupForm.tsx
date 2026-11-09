"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Field, FormAlert, PasswordField, formStyles } from "@/components/forms/Field";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { ApiError, waitMessage } from "@/lib/errors";
import { loginHref, safeNextPath } from "@/lib/next-path";
import type { Me } from "@/lib/types";

// The backend's limits (A-159). The backend's answer is final; these only save a trip.
const PASSWORD_MIN = 10;
const PASSWORD_MAX = 128;

// Consent text, version signup-v1 to match the backend (A-160).
export const CONSENT_TEXT =
  "I agree that CompanyA may use my name, email and phone number to manage my account and bookings, and to contact me about them.";

type FieldName = "full_name" | "email" | "password" | "phone" | "consent";
const FIELD_FOR_CODE: Record<string, FieldName> = {
  invalid_name: "full_name",
  invalid_email: "email",
  email_taken: "email",
  weak_password: "password",
  invalid_phone: "phone",
  consent_required: "consent",
};

export function SignupForm() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const { signedIn } = useSession();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [problem, setProblem] = useState<React.ReactNode>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      full_name: String(form.get("full_name") ?? "").trim(),
      email: String(form.get("email") ?? "").trim(),
      password: String(form.get("password") ?? ""),
      phone: String(form.get("phone") ?? "").trim() || null,
      consent: form.get("consent") === "on",
    };
    const found: Partial<Record<FieldName, string>> = {};
    if (!body.full_name) found.full_name = "Enter your name.";
    if (!body.email) found.email = "Enter your email address.";
    if (body.password.length < PASSWORD_MIN || body.password.length > PASSWORD_MAX)
      found.password = `Use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`;
    if (!body.consent) found.consent = "Please agree so we can manage your bookings.";
    setErrors(found);
    setProblem(null);
    if (Object.keys(found).length) return;

    setBusy(true);
    try {
      const me = await api<Me>("/api/auth/signup", { method: "POST", body });
      signedIn(me); // the backend signs the new account in straight away
      router.replace(next);
    } catch (error) {
      setBusy(false);
      if (error instanceof ApiError && FIELD_FOR_CODE[error.code]) {
        const message =
          error.code === "email_taken" ? "An account with this email already exists." : error.message;
        setErrors({ [FIELD_FOR_CODE[error.code]]: message });
        if (error.code === "email_taken") {
          setProblem(
            <p>
              An account with this email already exists. <Link href={loginHref(next)}>Log in instead</Link>.
            </p>,
          );
        }
        return;
      }
      if (error instanceof ApiError && error.code === "rate_limited") {
        setProblem(<p>{waitMessage(error)}</p>);
        return;
      }
      setProblem(<p>{error instanceof ApiError ? error.message : "Something went wrong. Please try again."}</p>);
    }
  }

  return (
    <form className={formStyles.form} onSubmit={submit} noValidate>
      {problem && <FormAlert>{problem}</FormAlert>}
      <Field label="Full name" name="full_name" autoComplete="name" required maxLength={200} error={errors.full_name} />
      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        required
        maxLength={320}
        error={errors.email}
      />
      <PasswordField
        label="Password"
        name="password"
        autoComplete="new-password"
        hint={`${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`}
        required
        minLength={PASSWORD_MIN}
        maxLength={PASSWORD_MAX}
        error={errors.password}
      />
      <Field
        label="Phone (optional)"
        name="phone"
        type="tel"
        autoComplete="tel"
        hint="For questions about your stay."
        maxLength={40}
        error={errors.phone}
      />
      <div>
        <label className={formStyles.check}>
          <input
            type="checkbox"
            name="consent"
            aria-invalid={errors.consent ? true : undefined}
            aria-describedby={errors.consent ? "consent-error" : undefined}
          />
          <span>
            {CONSENT_TEXT}{" "}
            <Link href="/privacy" target="_blank" rel="noopener">
              How we use your details
            </Link>
          </span>
        </label>
        {errors.consent && (
          <span id="consent-error" className={formStyles.error}>
            {errors.consent}
          </span>
        )}
      </div>
      <div className={formStyles.actions}>
        <button type="submit" className="button" disabled={busy}>
          {busy ? "Creating your account" : "Create account"}
        </button>
      </div>
      <p>
        Already have an account? <Link href={loginHref(next)}>Log in</Link>
      </p>
    </form>
  );
}
