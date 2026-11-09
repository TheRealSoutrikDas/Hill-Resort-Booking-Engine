"use client";

import { useCallback, useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { api } from "@/lib/api";
import { loadNames, type Names } from "@/lib/catalogue";
import { ApiError } from "@/lib/errors";
import { formatInr } from "@/lib/format";
import { addDays, todayInIndia } from "@/lib/stay";
import type { Inventory } from "@/lib/types";
import styles from "../admin.module.css";

const DEFAULT_NIGHTS = 14; // A-181
const MAX_NIGHTS = 62; // the backend's calendar limit (A-101)
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; // 0 = Monday, as the API

function dayLabel(iso: string) {
  const d = new Date(`${iso}T00:00:00Z`);
  return {
    weekday: d.toLocaleDateString("en-IN", { weekday: "short", timeZone: "UTC" }),
    day: d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }),
    weekend: d.getUTCDay() === 5 || d.getUTCDay() === 6, // Friday and Saturday nights
  };
}

export function InventoryAdmin() {
  const [from, setFrom] = useState(() => todayInIndia());
  const [to, setTo] = useState(() => addDays(todayInIndia(), DEFAULT_NIGHTS - 1));
  const [data, setData] = useState<Inventory | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [plan, setPlan] = useState("RO");
  const [version, setVersion] = useState(0); // bumped after a change to reload the grid
  const [names, setNames] = useState<Names | null>(null);

  useEffect(() => {
    let current = true;
    loadNames()
      .then((n) => current && setNames(n))
      .catch(() => undefined); // plan codes are shown instead
    return () => {
      current = false;
    };
  }, []);
  const planName = (code: string) => names?.plans.get(code) ?? code;

  useEffect(() => {
    let current = true;
    api<Inventory>(`/api/admin/inventory?from=${from}&to=${to}`)
      .then((d) => {
        if (!current) return;
        setData(d);
        setProblem(null);
      })
      .catch((error: unknown) => {
        if (current) setProblem(error instanceof ApiError ? error.message : "The calendar could not be loaded.");
      });
    return () => {
      current = false;
    };
  }, [from, to, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const roomTypes = data?.room_types ?? [];
  const plans = Object.keys(roomTypes[0]?.nights[0]?.rates ?? { RO: 0 });
  const dates = roomTypes[0]?.nights.map((n) => n.date) ?? [];

  return (
    <>
      <h1>Inventory</h1>
      <div className={styles.toolbar}>
        <label>
          From
          <input type="date" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} />
        </label>
        <label>
          To
          <input
            type="date"
            value={to}
            min={from}
            max={addDays(from, MAX_NIGHTS - 1)}
            onChange={(e) => e.target.value && setTo(e.target.value)}
          />
        </label>
        <label>
          Prices shown for
          <select value={plan} onChange={(e) => setPlan(e.target.value)}>
            {plans.map((p) => (
              <option key={p} value={p}>
                {planName(p)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      {!data && !problem && <p className="muted">Loading the calendar.</p>}
      {data && (
        <>
        <p className="muted" id="grid-help">
          Each night: rooms left for web booking out of the web allotment, then sold and held, then the price for one
          night ({planName(plan)}), before GST.
        </p>
        <div className={styles.gridBox} role="region" aria-label="Inventory calendar" aria-describedby="grid-help" tabIndex={0}>
          <table className={styles.grid}>
            <caption className="visually-hidden">
              Inventory from {data.from_date} to {data.to_date}
            </caption>
            <thead>
              <tr>
                <th scope="col">Room type</th>
                {dates.map((d) => {
                  const l = dayLabel(d);
                  return (
                    <th key={d} scope="col" className={l.weekend ? styles.weekend : undefined}>
                      {l.weekday}
                      <br />
                      {l.day}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {roomTypes.map((rt) => (
                <tr key={rt.code}>
                  <th scope="row">
                    {rt.name}
                    <br />
                    <span className={styles.small}>{rt.total_units} rooms in all</span>
                  </th>
                  {rt.nights.map((n) => (
                    <td
                      key={n.date}
                      className={n.is_blackout ? styles.closed : dayLabel(n.date).weekend ? styles.weekend : undefined}
                      data-testid={`cell-${rt.code}-${n.date}`}
                    >
                      <div className={styles.cell}>
                        {n.is_blackout ? (
                          <span>Closed</span>
                        ) : (
                          <span className={`${styles.avail} ${n.available === 0 ? styles.full : ""}`}>
                            {n.available}/{n.total_for_web}
                          </span>
                        )}
                        <span className={styles.small}>
                          {n.sold} sold, {n.held} held
                        </span>
                        <span>{n.rates[plan] != null ? formatInr(n.rates[plan]) : "No price"}</span>
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </>
      )}

      <div className={styles.forms}>
        <RateForm roomTypes={roomTypes} plans={plans} planName={planName} onDone={reload} />
        <AllotmentForm roomTypes={roomTypes} onDone={reload} />
        <BlackoutForm roomTypes={roomTypes} onDone={reload} />
      </div>
    </>
  );
}

type RT = Inventory["room_types"];
type Result = { ok: string } | { error: string; nights?: string[] } | null;

function ResultNote({ result }: { result: Result }) {
  if (!result) return null;
  if ("ok" in result) return <p className={styles.ok} role="status">{result.ok}</p>;
  return (
    <FormAlert>
      <p>{result.error}</p>
      {result.nights && result.nights.length > 0 && (
        <ul className={styles.nights}>
          {result.nights.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </FormAlert>
  );
}

/** A-183: the backend rejects the whole change and lists each night that blocks it. */
function failure(error: unknown): Result {
  if (!(error instanceof ApiError)) return { error: "The change could not be saved. Please try again." };
  const details = error.details as { nights?: { date: string; sold?: number; held?: number; minimum?: number }[] } | null;
  const nights = details?.nights?.map((n) =>
    n.minimum !== undefined ? `${n.date}: ${n.sold} sold and ${n.held} held, so at least ${n.minimum}` : `${n.date}`,
  );
  return { error: error.message, nights };
}

function nightsChanged(n: number) {
  return `${n} ${n === 1 ? "night" : "nights"} changed.`;
}

function RangeFields({ from, to, setFrom, setTo }: { from: string; to: string; setFrom: (v: string) => void; setTo: (v: string) => void }) {
  return (
    <div className={styles.row}>
      <label>
        From
        <input type="date" required value={from} onChange={(e) => setFrom(e.target.value)} />
      </label>
      <label>
        To (inclusive)
        <input type="date" required value={to} min={from} onChange={(e) => setTo(e.target.value)} />
      </label>
    </div>
  );
}

function RateForm({
  roomTypes,
  plans,
  planName,
  onDone,
}: {
  roomTypes: RT;
  plans: string[];
  planName: (code: string) => string;
  onDone: () => void;
}) {
  const [roomType, setRoomType] = useState("");
  const [plan, setPlan] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [rupees, setRupees] = useState("");
  const [days, setDays] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const out = await api<{ nights_changed: number }>("/api/admin/rates", {
        method: "PUT",
        body: {
          room_type: roomType || roomTypes[0]?.code,
          rate_plan: plan || plans[0],
          from_date: from,
          to_date: to,
          price_paise: Math.round(Number(rupees) * 100), // A-182: whole rupees to paise
          weekdays: days.length ? days : null,
        },
      });
      setResult({ ok: nightsChanged(out.nights_changed) });
      onDone();
    } catch (error) {
      setResult(failure(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={submit} aria-labelledby="rate-title">
      <h2 id="rate-title">Set a price</h2>
      <div className={styles.row}>
        <label>
          Room type
          <select value={roomType} onChange={(e) => setRoomType(e.target.value)}>
            {roomTypes.map((r) => (
              <option key={r.code} value={r.code}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Rate plan
          <select value={plan} onChange={(e) => setPlan(e.target.value)}>
            {plans.map((p) => (
              <option key={p} value={p}>
                {planName(p)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <RangeFields from={from} to={to} setFrom={setFrom} setTo={setTo} />
      <fieldset className={styles.days}>
        <legend>Only on (leave empty for every night)</legend>
        {WEEKDAYS.map((label, i) => (
          <label key={label}>
            <input
              type="checkbox"
              checked={days.includes(i)}
              onChange={(e) => setDays((d) => (e.target.checked ? [...d, i].sort() : d.filter((x) => x !== i)))}
            />
            {label}
          </label>
        ))}
      </fieldset>
      <label>
        Price per room per night, in rupees, before GST
        <input type="number" required min={1} step={1} value={rupees} onChange={(e) => setRupees(e.target.value)} />
      </label>
      <ResultNote result={result} />
      <button type="submit" className="button" disabled={busy}>
        {busy ? "Saving" : "Set price"}
      </button>
    </form>
  );
}

function AllotmentForm({ roomTypes, onDone }: { roomTypes: RT; onDone: () => void }) {
  const [roomType, setRoomType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [count, setCount] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);
  const chosen = roomTypes.find((r) => r.code === (roomType || roomTypes[0]?.code));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const out = await api<{ nights_changed: number }>("/api/admin/allotment", {
        method: "PUT",
        body: { room_type: chosen?.code, from_date: from, to_date: to, total_for_web: Number(count) },
      });
      setResult({ ok: nightsChanged(out.nights_changed) });
      onDone();
    } catch (error) {
      setResult(failure(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={submit} aria-labelledby="allotment-title">
      <h2 id="allotment-title">Set the web allotment</h2>
      <p className="muted">How many rooms of this type can be booked online each night.</p>
      <label>
        Room type
        <select value={roomType} onChange={(e) => setRoomType(e.target.value)}>
          {roomTypes.map((r) => (
            <option key={r.code} value={r.code}>
              {r.name}
            </option>
          ))}
        </select>
      </label>
      <RangeFields from={from} to={to} setFrom={setFrom} setTo={setTo} />
      <label>
        Rooms for web booking{chosen ? ` (at most ${chosen.total_units})` : ""}
        <input
          type="number"
          required
          min={0}
          max={chosen?.total_units}
          step={1}
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
      </label>
      <ResultNote result={result} />
      <button type="submit" className="button" disabled={busy}>
        {busy ? "Saving" : "Set allotment"}
      </button>
    </form>
  );
}

function BlackoutForm({ roomTypes, onDone }: { roomTypes: RT; onDone: () => void }) {
  const [codes, setCodes] = useState<string[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [close, setClose] = useState(true);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);

  const which = codes.length === 0 ? "all room types" : codes.length === 1 ? "1 room type" : `${codes.length} room types`;
  const span = from && to && to >= from ? Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000) + 1 : 0;

  async function send() {
    setBusy(true);
    setResult(null);
    try {
      const out = await api<{ nights_changed: number; nights_with_bookings: number }>("/api/admin/blackouts", {
        method: "PUT",
        body: { from_date: from, to_date: to, blackout: close, room_types: codes.length ? codes : null },
      });
      const kept = out.nights_with_bookings
        ? ` ${out.nights_with_bookings} of them have confirmed bookings, which are honoured.`
        : "";
      setResult({ ok: `${nightsChanged(out.nights_changed)}${close ? kept : ""}` });
      onDone();
    } catch (error) {
      setResult(failure(error));
    } finally {
      setBusy(false);
      setAsking(false);
    }
  }

  return (
    <form
      className={styles.form}
      aria-labelledby="blackout-title"
      onSubmit={(e) => {
        e.preventDefault();
        // A-183: closing nights stops sales, so it asks for a second click.
        if (close) setAsking(true);
        else void send();
      }}
    >
      <h2 id="blackout-title">Black out or reopen</h2>
      <fieldset className={styles.days}>
        <legend>Room types (none ticked means all)</legend>
        {roomTypes.map((r) => (
          <label key={r.code}>
            <input
              type="checkbox"
              checked={codes.includes(r.code)}
              onChange={(e) => setCodes((c) => (e.target.checked ? [...c, r.code] : c.filter((x) => x !== r.code)))}
            />
            {r.name}
          </label>
        ))}
      </fieldset>
      <RangeFields from={from} to={to} setFrom={setFrom} setTo={setTo} />
      <fieldset className={styles.days}>
        <legend>Action</legend>
        <label>
          <input type="radio" name="blackout-action" checked={close} onChange={() => setClose(true)} />
          Black out (stop sales)
        </label>
        <label>
          <input type="radio" name="blackout-action" checked={!close} onChange={() => setClose(false)} />
          Reopen
        </label>
      </fieldset>
      <ResultNote result={result} />
      {asking ? (
        <div className={styles.row}>
          <p>
            <strong>
              Black out {span} {span === 1 ? "night" : "nights"} for {which}?
            </strong>
          </p>
          <button type="button" className="button" disabled={busy} onClick={send}>
            {busy ? "Saving" : "Yes, black out"}
          </button>
          <button type="button" className="button-quiet" disabled={busy} onClick={() => setAsking(false)}>
            Keep them open
          </button>
        </div>
      ) : (
        <button type="submit" className="button" disabled={busy}>
          {close ? "Black out" : "Reopen"}
        </button>
      )}
    </form>
  );
}
