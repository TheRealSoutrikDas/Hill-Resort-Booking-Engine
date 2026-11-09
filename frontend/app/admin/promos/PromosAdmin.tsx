"use client";

import { useCallback, useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { addDays, todayInIndia } from "@/lib/stay";
import type { AdminPromo } from "@/lib/types";
import styles from "../admin.module.css";

export function PromosAdmin() {
  const [promos, setPromos] = useState<AdminPromo[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    api<AdminPromo[]>("/api/admin/promos")
      .then((p) => current && setPromos(p))
      .catch(() => current && setProblem("Promo codes could not be loaded. Refresh the page to try again."));
    return () => {
      current = false;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  return (
    <>
      <h1>Promo codes</h1>
      <p className="muted">
        A code&apos;s name and discount are fixed once created. You can switch it off, move its end date or change its
        limit. Codes are never deleted, because bookings refer to them.
      </p>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      {!promos && !problem && <p className="muted">Loading promo codes.</p>}
      {promos && promos.length === 0 && <p className="muted">No promo codes yet. Create the first one below.</p>}
      {promos && promos.length > 0 && (
        <div className={styles.gridBox} role="region" aria-label="Promo codes" tabIndex={0}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Off</th>
                <th scope="col">Valid</th>
                <th scope="col">Used</th>
                <th scope="col">Reserved</th>
                <th scope="col">Limit</th>
                <th scope="col">Today</th>
                <th scope="col">Change</th>
              </tr>
            </thead>
            <tbody>
              {promos.map((p) => (
                <PromoRow key={p.code} promo={p} onDone={reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className={styles.forms}>
        <CreatePromo onDone={reload} />
      </div>
    </>
  );
}

function PromoRow({ promo, onDone }: { promo: AdminPromo; onDone: () => void }) {
  const [editing, setEditing] = useState(false);
  const [validTo, setValidTo] = useState(promo.valid_to);
  const [cap, setCap] = useState(promo.max_uses === null ? "" : String(promo.max_uses));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function update(body: Record<string, unknown>) {
    setBusy(true);
    setProblem(null);
    try {
      await api(`/api/admin/promos/${encodeURIComponent(promo.code)}`, { method: "PATCH", body });
      setEditing(false);
      onDone();
    } catch (error) {
      const details = error instanceof ApiError ? (error.details as { minimum?: number } | null) : null;
      setProblem(
        error instanceof ApiError
          ? `${error.message}${details?.minimum !== undefined ? ` The lowest limit allowed now is ${details.minimum}.` : ""}`
          : "The change could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr>
      <th scope="row">{promo.code}</th>
      <td>{promo.percent_off}%</td>
      <td>
        {promo.valid_from} to {promo.valid_to}
      </td>
      <td>{promo.used}</td>
      <td>{promo.reserved}</td>
      <td>{promo.max_uses === null ? "No limit" : `${promo.max_uses} (${promo.uses_left} left)`}</td>
      <td>
        <span className={`${styles.badge} ${promo.usable_today ? styles.on : styles.off}`}>
          {promoState(promo)}
        </span>
      </td>
      <td>
        <div className={styles.row}>
          <button
            type="button"
            className="button-quiet"
            disabled={busy}
            onClick={() => update({ is_active: !promo.is_active })}
            aria-label={`${promo.is_active ? "Switch off" : "Switch on"} ${promo.code}`}
          >
            {promo.is_active ? "Switch off" : "Switch on"}
          </button>
          {!editing && (
            <button type="button" className="button-quiet" onClick={() => setEditing(true)} aria-label={`Edit ${promo.code}`}>
              Edit dates or limit
            </button>
          )}
        </div>
        {editing && (
          <form
            className={styles.row}
            onSubmit={(e) => {
              e.preventDefault();
              void update({ valid_to: validTo, max_uses: cap === "" ? null : Number(cap) });
            }}
          >
            <label>
              Ends
              <input type="date" value={validTo} required onChange={(e) => setValidTo(e.target.value)} />
            </label>
            <label>
              Limit (empty for none)
              <input type="number" min={0} step={1} value={cap} onChange={(e) => setCap(e.target.value)} />
            </label>
            <button type="submit" className="button" disabled={busy}>
              Save
            </button>
            <button type="button" className="button-quiet" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </form>
        )}
        {problem && (
          <p role="alert" className={styles.full}>
            {problem}
          </p>
        )}
      </td>
    </tr>
  );
}

function CreatePromo({ onDone }: { onDone: () => void }) {
  const today = todayInIndia();
  const [code, setCode] = useState("");
  const [percent, setPercent] = useState("");
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(addDays(today, 30));
  const [cap, setCap] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok?: string; error?: string } | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const created = await api<AdminPromo>("/api/admin/promos", {
        method: "POST",
        body: {
          code: code.trim().toUpperCase(),
          percent_off: Number(percent),
          valid_from: from,
          valid_to: to,
          max_uses: cap === "" ? null : Number(cap),
        },
      });
      setMessage({ ok: `${created.code} created.` });
      setCode("");
      setPercent("");
      setCap("");
      onDone();
    } catch (error) {
      setMessage({ error: error instanceof ApiError ? error.message : "The code could not be created." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={submit} aria-labelledby="create-title">
      <h2 id="create-title">Create a promo code</h2>
      <div className={styles.row}>
        <label>
          Code (3 to 32 letters and digits)
          <input value={code} required minLength={3} maxLength={32} pattern="[A-Za-z0-9]{3,32}" onChange={(e) => setCode(e.target.value)} />
        </label>
        <label>
          Percent off (1 to 90)
          <input type="number" required min={1} max={90} step={1} value={percent} onChange={(e) => setPercent(e.target.value)} />
        </label>
      </div>
      <div className={styles.row}>
        <label>
          Valid from
          <input type="date" required value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label>
          Valid to (inclusive)
          <input type="date" required value={to} min={from} onChange={(e) => setTo(e.target.value)} />
        </label>
        <label>
          Limit (empty for none)
          <input type="number" min={1} step={1} value={cap} onChange={(e) => setCap(e.target.value)} />
        </label>
      </div>
      {message?.ok && (
        <p className={styles.ok} role="status">
          {message.ok}
        </p>
      )}
      {message?.error && (
        <FormAlert>
          <p>{message.error}</p>
        </FormAlert>
      )}
      <button type="submit" className="button" disabled={busy}>
        {busy ? "Creating" : "Create code"}
      </button>
    </form>
  );
}

/** Why a code does or does not work today, in that order of importance. */
function promoState(p: AdminPromo): string {
  if (p.usable_today) return "Works";
  if (!p.is_active) return "Switched off";
  const today = todayInIndia();
  if (today < p.valid_from) return "Not started";
  if (today > p.valid_to) return "Ended";
  if (p.uses_left !== null && p.uses_left <= 0) return "Limit reached";
  return "Not usable today";
}
