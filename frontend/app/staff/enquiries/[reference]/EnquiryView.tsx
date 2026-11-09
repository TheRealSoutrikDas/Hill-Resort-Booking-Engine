"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { CATEGORIES, FIELD_LABELS, LANES, REASONS, TEAMS, atIndia, laneLabel } from "@/lib/lanes";
import type { EnquiryDetail, HistoryEntry } from "@/lib/types";
import styles from "../../staff.module.css";

type Fields = Record<string, string | number | null | undefined>;

export function EnquiryView() {
  const { reference } = useParams<{ reference: string }>();
  const { me } = useSession();
  const [enquiry, setEnquiry] = useState<EnquiryDetail | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    api<EnquiryDetail>(`/api/enquiries/${encodeURIComponent(reference)}`)
      .then((e) => current && setEnquiry(e))
      .catch(
        (error: unknown) =>
          current &&
          setProblem(error instanceof ApiError && error.status === 404 ? "No enquiry with this reference." : "This enquiry could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [reference]);

  if (problem) {
    return (
      <FormAlert>
        <p>{problem}</p>
      </FormAlert>
    );
  }
  if (!enquiry) return <p className="muted">Loading the enquiry.</p>;
  const e = enquiry;
  const isGm = !!me?.is_gm;

  return (
    <>
      <p>
        <Link href={`/staff/inbox?tab=${e.lane ?? e.status}`}>Back to {laneLabel(e.lane)}</Link>
      </p>
      <div className={styles.head}>
        <h1>{e.reference}</h1>
        <span>
          <span className={styles.badge}>{laneLabel(e.lane)}</span>{" "}
          <span className={styles.badge}>{statusLabel(e.status)}</span>
        </span>
      </div>

      {e.alert && (
        <p className={`${styles.note} ${styles.warn}`}>
          GM alert raised {atIndia(e.alert.created_at)} ({e.alert.reason}).{" "}
          {e.alert.acknowledged_at
            ? `Acknowledged by ${e.alert.acknowledged_by} on ${atIndia(e.alert.acknowledged_at)}.`
            : "Not yet acknowledged."}
        </p>
      )}
      {e.status === "failed" && (
        <p className={`${styles.note} ${styles.warn}`}>
          Classification failed ({e.error ?? "unknown error"}). The enquiry is saved; run the classification again below.
        </p>
      )}

      <div className={styles.grid}>
        <section className={styles.panel} aria-labelledby="message-title">
          <h2 id="message-title">Message</h2>
          <p className={styles.message}>{e.message}</p>
          <dl className={styles.facts}>
            <dt>From</dt>
            <dd>{e.contact_name}</dd>
            {e.contact_email && (
              <>
                <dt>Email</dt>
                <dd>{e.contact_email}</dd>
              </>
            )}
            {e.contact_phone && (
              <>
                <dt>Phone</dt>
                <dd>{e.contact_phone}</dd>
              </>
            )}
            <dt>Received</dt>
            <dd>
              {atIndia(e.received_at)}, by {e.channel}
            </dd>
          </dl>
        </section>

        <section className={styles.panel} aria-labelledby="extracted-title">
          <h2 id="extracted-title">What was understood</h2>
          <dl className={styles.facts}>
            <dt>Category</dt>
            <dd>{e.category ? CATEGORIES[e.category] ?? e.category : "Not yet classified"}</dd>
            <dt>Lane</dt>
            <dd>
              {laneLabel(e.lane)}
              {e.owner_team ? `, ${TEAMS[e.owner_team] ?? e.owner_team} team` : ""}
            </dd>
            {e.confidence !== null && (
              <>
                <dt>Confidence</dt>
                <dd>{Math.round(e.confidence * 100)}%</dd>
              </>
            )}
            {e.backend && (
              <>
                <dt>Classified by</dt>
                <dd>
                  {e.backend}
                  {e.is_fallback ? ` (the AI was unavailable: ${e.error ?? "fallback"})` : ""}
                </dd>
              </>
            )}
            {Object.entries(e.fields ?? {}).map(([k, v]) => (
              <FieldFact key={k} name={k} value={v as string | number} />
            ))}
          </dl>
          {e.lane === "unsorted" && e.lane_reasons.length > 0 && (
            <div>
              <strong>Why it is in Unsorted</strong>
              <ul className={styles.history}>
                {e.lane_reasons.map((r) => (
                  <li key={r}>{REASONS[r] ?? r}</li>
                ))}
              </ul>
            </div>
          )}
          <Outputs keyword={e.keyword_output} model={e.model_output} />
        </section>
      </div>

      <div className={styles.grid} style={{ marginTop: "var(--space-4)" }}>
        <div className={styles.stack}>
          {e.reply_text ? (
            <section className={styles.panel} aria-labelledby="reply-title">
              <h2 id="reply-title">Reply sent</h2>
              <p className="muted">
                By {e.replied_by} on {atIndia(e.replied_at)}. Simulated: nothing was sent to the guest.
              </p>
              <p className={styles.message}>{e.reply_text}</p>
            </section>
          ) : (
            e.can_act && <ReplyEditor enquiry={e} onDone={setEnquiry} />
          )}
          {e.can_act && <CorrectForm enquiry={e} onDone={setEnquiry} />}
          {e.can_act && <RouteForm enquiry={e} onDone={setEnquiry} />}
        </div>
        <div className={styles.stack}>
          <Approval enquiry={e} isGm={isGm} onDone={setEnquiry} />
          {e.can_reclassify && <Rerun enquiry={e} onDone={setEnquiry} />}
          <History entries={e.history} />
        </div>
      </div>
    </>
  );
}

function statusLabel(s: string) {
  return { pending: "Pending", classified: "Classified", failed: "Failed", replied: "Replied" }[s] ?? s;
}

function FieldFact({ name, value }: { name: string; value: string | number }) {
  const shown = name === "budget_inr" && typeof value === "number" ? value.toLocaleString("en-IN") : String(value);
  return (
    <>
      <dt>{FIELD_LABELS[name] ?? name}</dt>
      <dd>{shown}</dd>
    </>
  );
}

function Outputs({ keyword, model }: { keyword: Record<string, unknown> | null; model: Record<string, unknown> | null }) {
  const describe = (o: Record<string, unknown> | null) => {
    if (!o) return "Not asked";
    const category = typeof o.category === "string" ? CATEGORIES[o.category] ?? o.category : "?";
    const confidence = typeof o.confidence === "number" ? `, ${Math.round(o.confidence * 100)}%` : "";
    return `${category}${confidence}`;
  };
  return (
    <details>
      <summary>What each check said</summary>
      <dl className={styles.facts} style={{ marginTop: "var(--space-2)" }}>
        <dt>Keyword check</dt>
        <dd>{describe(keyword)}</dd>
        <dt>AI model</dt>
        <dd>{describe(model)}</dd>
      </dl>
    </details>
  );
}

// ---------- reply (A-188) ----------

const PLACEHOLDER = /\{(guest_name|room_type|dates|guests|price_total|event_month)\}/g;

function ReplyEditor({ enquiry, onDone }: { enquiry: EnquiryDetail; onDone: (e: EnquiryDetail) => void }) {
  const [text, setText] = useState(enquiry.draft_reply ?? "");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const missing = [...new Set([...text.matchAll(PLACEHOLDER)].map((m) => m[0]))];

  async function send(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      onDone(await api<EnquiryDetail>(`/api/enquiries/${enquiry.reference}/reply`, { method: "POST", body: { text } }));
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "The reply could not be recorded.");
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="draft-title">
      <h2 id="draft-title">Reply</h2>
      <p className="muted">
        A draft written from a template, with prices worked out by the booking system. Edit it before sending. Simulated:
        nothing is sent to the guest.
      </p>
      <form className={styles.form} onSubmit={send}>
        <label>
          Reply text
          <textarea value={text} maxLength={5000} onChange={(ev) => setText(ev.target.value)} />
        </label>
        {missing.length > 0 && (
          <div>
            <strong>Still to fill in:</strong>
            <ul className={styles.todo} aria-label="Placeholders still in the reply">
              {missing.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        )}
        {problem && (
          <FormAlert>
            <p>{problem}</p>
          </FormAlert>
        )}
        <div className={styles.actions}>
          <button type="submit" className="button" disabled={busy || missing.length > 0 || !text.trim()}>
            {busy ? "Sending" : "Send reply"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------- correct (A-189) ----------

const FIELD_INPUTS: { name: string; type: "date" | "month" | "number" | "select" }[] = [
  { name: "check_in", type: "date" },
  { name: "check_out", type: "date" },
  { name: "event_month", type: "month" },
  { name: "guests", type: "number" },
  { name: "nights", type: "number" },
  { name: "budget_inr", type: "number" },
  { name: "room_type", type: "select" },
];
const ROOM_TYPES = ["DLX", "EVR", "FST", "PLV", "PPV"];

function CorrectForm({ enquiry, onDone }: { enquiry: EnquiryDetail; onDone: (e: EnquiryDetail) => void }) {
  const current = (enquiry.fields ?? {}) as Fields;
  const [category, setCategory] = useState(enquiry.category ?? "");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELD_INPUTS.map((f) => [f.name, current[f.name] == null ? "" : String(current[f.name])])),
  );
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    // Only what changed is sent; an emptied field is sent as null, which clears it.
    const fields: Record<string, string | number | null> = {};
    for (const f of FIELD_INPUTS) {
      const before = current[f.name] == null ? "" : String(current[f.name]);
      const after = values[f.name] ?? "";
      if (after !== before) fields[f.name] = after === "" ? null : f.type === "number" ? Number(after) : after;
    }
    const body: Record<string, unknown> = {};
    if (category && category !== enquiry.category) body.category = category;
    if (Object.keys(fields).length) body.fields = fields;
    setBusy(true);
    setProblem(null);
    try {
      onDone(await api<EnquiryDetail>(`/api/enquiries/${enquiry.reference}`, { method: "PATCH", body }));
    } catch (error) {
      const names = error instanceof ApiError ? (error.details as { fields?: string[] } | null)?.fields : undefined;
      setProblem(
        error instanceof ApiError
          ? `${error.message}${names?.length ? ` (${names.map((n) => FIELD_LABELS[n] ?? n).join(", ")})` : ""}`
          : "The correction could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="correct-title">
      <h2 id="correct-title">Correct</h2>
      <p className="muted">Changing the category moves the enquiry to that lane and rewrites the draft.</p>
      <form className={styles.form} onSubmit={save}>
        <label>
          Category
          <select value={category} onChange={(ev) => setCategory(ev.target.value)}>
            {Object.entries(CATEGORIES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <div className={styles.fields}>
          {FIELD_INPUTS.map((f) => (
            <label key={f.name}>
              {FIELD_LABELS[f.name]}
              {f.type === "select" ? (
                <select value={values[f.name]} onChange={(ev) => setValues((v) => ({ ...v, [f.name]: ev.target.value }))}>
                  <option value="">None</option>
                  {ROOM_TYPES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={f.type}
                  min={f.type === "number" ? 1 : undefined}
                  value={values[f.name]}
                  onChange={(ev) => setValues((v) => ({ ...v, [f.name]: ev.target.value }))}
                />
              )}
            </label>
          ))}
        </div>
        {problem && (
          <FormAlert>
            <p>{problem}</p>
          </FormAlert>
        )}
        <div className={styles.actions}>
          <button type="submit" className="button" disabled={busy}>
            {busy ? "Saving" : "Save correction"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------- re-route ----------

function RouteForm({ enquiry, onDone }: { enquiry: EnquiryDetail; onDone: (e: EnquiryDetail) => void }) {
  const [lane, setLane] = useState(enquiry.lane ?? "unsorted");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function move(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      onDone(await api<EnquiryDetail>(`/api/enquiries/${enquiry.reference}/route`, { method: "POST", body: { lane } }));
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "The enquiry could not be moved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="route-title">
      <h2 id="route-title">Move to another lane</h2>
      <p className="muted">The category stays as it is. Moving to Complaint alerts the GM.</p>
      <form className={`${styles.form} ${styles.actions}`} onSubmit={move}>
        <label>
          Lane
          <select value={lane} onChange={(ev) => setLane(ev.target.value)}>
            {LANES.map((l) => (
              <option key={l.key} value={l.key}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="button-quiet" disabled={busy || lane === enquiry.lane}>
          {busy ? "Moving" : "Move"}
        </button>
      </form>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
    </section>
  );
}

// ---------- approve (A-190), re-run, history ----------

function Approval({ enquiry, isGm, onDone }: { enquiry: EnquiryDetail; isGm: boolean; onDone: (e: EnquiryDetail) => void }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  if (enquiry.verified_at) {
    return (
      <section className={styles.panel} aria-labelledby="approval-title">
        <h2 id="approval-title">Approved</h2>
        <p>
          The GM ({enquiry.verified_by}) approved this classification on {atIndia(enquiry.verified_at)}. It can no longer be
          changed.
        </p>
      </section>
    );
  }
  if (!isGm || !enquiry.can_verify) return null;
  return (
    <section className={styles.panel} aria-labelledby="approval-title">
      <h2 id="approval-title">Approve</h2>
      <p className="muted">
        Confirms the category, lane and details as they stand now. It is then fixed, and counts towards AI accuracy.
      </p>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      <button
        type="button"
        className="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setProblem(null);
          try {
            onDone(await api<EnquiryDetail>(`/api/enquiries/${enquiry.reference}/verify`, { method: "POST" }));
          } catch (error) {
            setProblem(error instanceof ApiError ? error.message : "The approval could not be saved.");
            setBusy(false);
          }
        }}
      >
        {busy ? "Approving" : "Approve classification"}
      </button>
    </section>
  );
}

function Rerun({ enquiry, onDone }: { enquiry: EnquiryDetail; onDone: (e: EnquiryDetail) => void }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <section className={styles.panel} aria-labelledby="rerun-title">
      <h2 id="rerun-title">Run the classification again</h2>
      <p className="muted">Possible until someone corrects, moves, replies to or approves it.</p>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      <button
        type="button"
        className="button-quiet"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setProblem(null);
          try {
            onDone(await api<EnquiryDetail>(`/api/enquiries/${enquiry.reference}/classify`, { method: "POST" }));
          } catch (error) {
            setProblem(error instanceof ApiError ? error.message : "The classification could not be run.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Running" : "Run again"}
      </button>
    </section>
  );
}

const ACTIONS: Record<string, string> = {
  correct: "corrected",
  reroute: "moved",
  reply: "replied",
  verify: "approved",
  reclassify: "ran the classification again",
};

function History({ entries }: { entries: HistoryEntry[] }) {
  return (
    <section className={styles.panel} aria-labelledby="history-title">
      <h2 id="history-title">History</h2>
      {entries.length === 0 ? (
        <p className="muted">No staff changes yet.</p>
      ) : (
        <ol className={styles.history}>
          {entries.map((h, i) => (
            <li key={i}>
              {atIndia(h.at)}: {h.by} {ACTIONS[h.action] ?? h.action}
              {h.field ? ` ${(FIELD_LABELS[h.field.replace("fields.", "")] ?? h.field.replace("fields.", "")).toLowerCase()}` : ""}
              {h.action === "correct" || h.action === "reroute" ? ` from ${show(h.old)} to ${show(h.new)}` : ""}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function show(v: unknown): string {
  if (v === null || v === undefined || v === "") return "nothing";
  if (typeof v === "string") return CATEGORIES[v] ?? laneLabel(v) ?? v;
  return String(v);
}
