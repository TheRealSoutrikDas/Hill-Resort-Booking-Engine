"use client";

import { useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { LANES, rateLabel } from "@/lib/lanes";
import { addDays, todayInIndia } from "@/lib/stay";
import type { MetricsOut } from "@/lib/types";
import styles from "../staff.module.css";

/** Every figure is counted by the backend; rates show count out of total (A-192). */
export function Metrics() {
  const [to, setTo] = useState(() => todayInIndia());
  const [from, setFrom] = useState(() => addDays(todayInIndia(), -29));
  const [data, setData] = useState<MetricsOut | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    api<MetricsOut>(`/api/enquiries/metrics?from=${from}&to=${to}`)
      .then((d) => {
        if (!current) return;
        setData(d);
        setProblem(null);
      })
      .catch((error: unknown) => current && setProblem(error instanceof ApiError ? error.message : "Metrics could not be loaded."));
    return () => {
      current = false;
    };
  }, [from, to]);

  return (
    <>
      <h1>Metrics</h1>
      <div className={styles.toolbar}>
        <label>
          From
          <input type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={to} min={from} onChange={(e) => e.target.value && setTo(e.target.value)} />
        </label>
      </div>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      {!data && !problem && <p className="muted">Loading metrics.</p>}
      {data && (
        <>
          <h2>Enquiries received</h2>
          <div className={styles.cards}>
            <Card label="Received" value={String(data.received)} />
            {LANES.map((l) => (
              <Card key={l.key} label={l.label} value={String(data.by_lane[l.key] ?? 0)} />
            ))}
            <Card label="Replied" value={String(data.replied)} />
            <Card label="Pending or failed" value={String(data.pending + data.failed)} />
          </div>

          <h2 style={{ marginTop: "var(--space-5)" }}>How routing went</h2>
          <div className={styles.cards}>
            <Card label="Sent to Unsorted" value={rateLabel(data.sent_to_unsorted)} note="Of classified enquiries" />
            <Card label="AI unavailable (keyword fallback)" value={rateLabel(data.fallback)} />
            <Card label="Category corrected by staff" value={rateLabel(data.category_corrected)} />
            <Card
              label="Median time to reply"
              value={data.median_minutes_to_reply === null ? "none yet" : minutes(data.median_minutes_to_reply)}
            />
          </div>

          <h2 style={{ marginTop: "var(--space-5)" }}>AI accuracy, checked by the GM</h2>
          <p className="muted">
            What the AI decided, compared with what the GM approved. {data.awaiting_approval} classified{" "}
            {data.awaiting_approval === 1 ? "enquiry is" : "enquiries are"} not yet approved, so not counted.
          </p>
          {Object.keys(data.ai_accuracy).length === 0 ? (
            <p className={styles.note}>No approved enquiries in this period yet.</p>
          ) : (
            <div className={styles.cards}>
              {Object.entries(data.ai_accuracy).map(([backend, a]) => (
                <div key={backend} className={styles.card}>
                  <p>
                    <strong>{backend}</strong>, {a.approved} approved
                  </p>
                  <p>Category right: {rateLabel(a.category)}</p>
                  <p>Lane right: {rateLabel(a.lane)}</p>
                  <p>Details right: {rateLabel(a.fields)}</p>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}

function Card({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={styles.card}>
      <p className={styles.meta}>{label}</p>
      <p className={styles.big}>{value}</p>
      {note && <p className={styles.meta}>{note}</p>}
    </div>
  );
}

function minutes(m: number): string {
  if (m < 60) return `${Math.round(m)} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${Math.round(m - h * 60)} min`;
}
