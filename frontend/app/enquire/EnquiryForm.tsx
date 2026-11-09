"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Field, FormAlert, formStyles } from "@/components/forms/Field";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { ApiError, waitMessage } from "@/lib/errors";
import type { Schemas } from "@/lib/types";
import styles from "./enquire.module.css";

const MAX_MESSAGE = 2000; // the backend's enquiry_max_length (A-114)

// Consent text, version enquiry-v1 to match the backend (A-177).
export const ENQUIRY_CONSENT_TEXT =
  "I agree that CompanyA may use my name and contact details to reply to this enquiry. The text of my message may be processed by an AI service to send it to the right team; my name, email and phone are never sent to it.";

type FieldName = "name" | "email" | "phone" | "message" | "consent";
const FIELDS_FOR_CODE: Record<string, FieldName[]> = {
  invalid_name: ["name"],
  invalid_email: ["email"],
  invalid_phone: ["phone"],
  contact_required: ["email", "phone"],
  empty_message: ["message"],
  message_too_long: ["message"],
  consent_required: ["consent"],
};

type Received = Schemas["EnquiryReceived"];

export function EnquiryForm() {
  const { me } = useSession();
  const messageId = useId();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [received, setReceived] = useState<Received | null>(null);
  const [formKey, setFormKey] = useState(0); // a new key gives a fresh, empty form

  if (received) {
    return (
      <section className={styles.received} aria-labelledby="received-title">
        <h2 id="received-title">Thank you</h2>
        <p>{received.message}</p>
        <p>
          Your reference is <strong className={styles.reference}>{received.reference}</strong>. Please keep it in
          case you contact us about this enquiry.
        </p>
        <p className="muted">No email copy is sent; emails are simulated in this demonstration.</p>
        <p>
          <button
            type="button"
            className="button-quiet"
            onClick={() => {
              setReceived(null);
              setMessage("");
              setFormKey((k) => k + 1);
            }}
          >
            Send another enquiry
          </button>
        </p>
      </section>
    );
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      name: String(form.get("name") ?? "").trim(),
      email: String(form.get("email") ?? "").trim() || null,
      phone: String(form.get("phone") ?? "").trim() || null,
      message: message.trim(),
      consent: form.get("consent") === "on",
    };
    const found: Partial<Record<FieldName, string>> = {};
    if (!body.name) found.name = "Please tell us your name.";
    if (!body.email && !body.phone) {
      found.email = found.phone = "Please give an email or a phone number so we can reply.";
    }
    if (!body.message) found.message = "Please write your message.";
    if (body.message.length > MAX_MESSAGE) found.message = `Please keep your message under ${MAX_MESSAGE} characters.`;
    if (!body.consent) found.consent = "Please agree so we can reply to you.";
    setErrors(found);
    setProblem(null);
    if (Object.keys(found).length) return;

    setBusy(true);
    try {
      setReceived(await api<Received>("/api/enquiries", { method: "POST", body }));
    } catch (error) {
      if (error instanceof ApiError && FIELDS_FOR_CODE[error.code]) {
        setErrors(Object.fromEntries(FIELDS_FOR_CODE[error.code].map((f) => [f, error.message])));
      } else if (error instanceof ApiError && error.code === "rate_limited") {
        setProblem(waitMessage(error));
      } else {
        setProblem(error instanceof ApiError ? error.message : "Your enquiry could not be sent. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  const left = MAX_MESSAGE - message.length;
  return (
    // Keyed on the account too: the session loads after the page, and the prefill
    // (A-176) is applied when it arrives. The message is kept in state, so it survives.
    <form key={`${formKey}-${me?.id ?? "guest"}`} className={`${formStyles.form} ${styles.form}`} onSubmit={submit} noValidate>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      <Field
        label="Your name"
        name="name"
        autoComplete="name"
        required
        maxLength={200}
        defaultValue={me?.role === "guest" ? me.full_name : ""}
        error={errors.name}
      />
      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        hint="An email or a phone number, so we can reply."
        maxLength={320}
        defaultValue={me?.role === "guest" ? me.email : ""}
        error={errors.email}
      />
      <Field
        label="Phone"
        name="phone"
        type="tel"
        autoComplete="tel"
        maxLength={40}
        defaultValue={me?.role === "guest" ? (me.phone ?? "") : ""}
        error={errors.phone}
      />
      <div className={formStyles.field}>
        <label htmlFor={messageId} className={formStyles.label}>
          Your message
        </label>
        <span id={`${messageId}-hint`} className={formStyles.hint}>
          Dates, number of guests and anything else that helps us answer.
        </span>
        <textarea
          id={messageId}
          name="message"
          className={`${formStyles.input} ${styles.message}`}
          rows={7}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          aria-invalid={errors.message ? true : undefined}
          aria-describedby={`${messageId}-hint ${messageId}-count${errors.message ? ` ${messageId}-error` : ""}`}
        />
        <span id={`${messageId}-count`} className={left < 0 ? formStyles.error : formStyles.hint} aria-live="polite">
          {left >= 0 ? `${left} characters left` : `${-left} characters over the limit`}
        </span>
        {errors.message && (
          <span id={`${messageId}-error`} className={formStyles.error}>
            {errors.message}
          </span>
        )}
      </div>
      <div>
        <label className={formStyles.check}>
          <input
            type="checkbox"
            name="consent"
            aria-invalid={errors.consent ? true : undefined}
            aria-describedby={errors.consent ? "enquiry-consent-error" : undefined}
          />
          <span>
            {ENQUIRY_CONSENT_TEXT}{" "}
            <Link href="/privacy" target="_blank" rel="noopener">
              How we use your details
            </Link>
          </span>
        </label>
        {errors.consent && (
          <span id="enquiry-consent-error" className={formStyles.error}>
            {errors.consent}
          </span>
        )}
      </div>
      <div className={formStyles.actions}>
        <button type="submit" className="button" disabled={busy}>
          {busy ? "Sending" : "Send enquiry"}
        </button>
      </div>
    </form>
  );
}
