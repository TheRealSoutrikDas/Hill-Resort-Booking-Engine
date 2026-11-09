"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PriceBreakdown } from "@/components/PriceBreakdown";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatInr, guestsLabel } from "@/lib/format";
import { MAX_ROOMS, searchQuery, stayLabel, type Line, type Search } from "@/lib/stay";
import type { PriceOut, RoomDetail } from "@/lib/types";
import { BookButton } from "./BookButton";
import styles from "./rooms.module.css";

type Props = {
  search: Search & { checkIn: string; checkOut: string };
  rooms: RoomDetail[];
  initialLines: Line[];
};

// Each answer remembers which choice it priced, so a price is shown (and booked) only
// while the choice on screen is still that one.
type QuoteState =
  | { state: "idle" }
  | { state: "ready"; key: string; price: PriceOut }
  | { state: "error"; key: string; message: string };

export function RoomChooser({ search, rooms, initialLines }: Props) {
  const byCode = useMemo(() => new Map(rooms.map((r) => [r.room.code, r])), [rooms]);
  const [lines, setLines] = useState<Line[]>(() =>
    initialLines.filter((l) => byCode.get(l.roomType)?.rate_plans.some((p) => p.code === l.ratePlan)),
  );
  const [quote, setQuote] = useState<QuoteState>({ state: "idle" });
  // A promo code is reserved with the hold, so it is entered here, before booking
  // (A-170 as amended): the backend accepts it only when the hold is created.
  const [promo, setPromo] = useState<string | null>(null);
  const [promoDraft, setPromoDraft] = useState("");
  const [promoError, setPromoError] = useState<string | null>(null);

  const key = JSON.stringify([lines, promo]);
  const totalRooms = lines.reduce((n, l) => n + l.units, 0);
  const totalGuests = lines.reduce((n, l) => n + l.guests, 0);

  // Keep the choice in the address bar: reloads, sharing and sign-in keep it (A-171).
  // history.replaceState updates the address without asking the server again.
  useEffect(() => {
    window.history.replaceState(null, "", `/rooms?${searchQuery(search, lines)}`);
  }, [lines, search]);

  // Ask the backend for the exact price whenever the choice changes (A-166).
  useEffect(() => {
    if (lines.length === 0) return;
    const controller = new AbortController();
    const quoted = JSON.stringify([lines, promo]);
    const timer = setTimeout(() => {
      api<PriceOut>("/api/quotes", {
        method: "POST",
        signal: controller.signal,
        body: {
          check_in: search.checkIn,
          check_out: search.checkOut,
          promo_code: promo,
          lines: lines.map((l) => ({ room_type: l.roomType, rate_plan: l.ratePlan, units: l.units, guests: l.guests })),
        },
      })
        .then((price) => setQuote({ state: "ready", key: quoted, price }))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          if (promo && error instanceof ApiError && (error.code === "invalid_promo_code" || error.code.startsWith("promo_"))) {
            // A bad code should not hide the price: show why, and price without it.
            setPromoError(error.message);
            setPromo(null);
            return;
          }
          setQuote({
            state: "error",
            key: quoted,
            message: error instanceof ApiError ? error.message : "The price could not be worked out.",
          });
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [lines, promo, search.checkIn, search.checkOut]);

  function lineFor(roomType: string, ratePlan: string) {
    return lines.find((l) => l.roomType === roomType && l.ratePlan === ratePlan);
  }

  function update(roomType: string, ratePlan: string, change: (l: Line) => Line | null) {
    setLines((current) =>
      current.flatMap((l) => {
        if (l.roomType !== roomType || l.ratePlan !== ratePlan) return [l];
        const next = change(l);
        return next ? [next] : [];
      }),
    );
  }

  function add(detail: RoomDetail, ratePlan: string) {
    const max = detail.room.max_guests;
    const remaining = Math.max(1, search.guests - totalGuests);
    setLines((current) => [...current, { roomType: detail.room.code, ratePlan, units: 1, guests: Math.min(max, remaining) }]);
  }

  function roomsOfType(code: string) {
    return lines.filter((l) => l.roomType === code).reduce((n, l) => n + l.units, 0);
  }

  return (
    <div className={styles.layout}>
      <ul className={styles.results}>
        {rooms.map((detail) => {
          const room = detail.room;
          const left = room.available_units ?? 0;
          const chosenOfType = roomsOfType(room.code);
          return (
            <li key={room.code} className={styles.room}>
              <div className={styles.roomHead}>
                <h2>
                  <Link href={`/rooms/${room.code}?${searchQuery(search)}`}>{room.name}</Link>
                </h2>
                <span className={left === 0 ? styles.soldOut : styles.left}>
                  {left === 0 ? "Sold out for these dates" : `${left} left for these dates`}
                </span>
              </div>
              <p className={styles.description}>
                {room.description} For up to {guestsLabel(room.max_guests)}.
              </p>
              {left > 0 && (
                <ul className={styles.plans}>
                  {(detail.quotes ?? []).map((q) => {
                    const line = lineFor(room.code, q.rate_plan.code);
                    const canAddRoom = totalRooms < MAX_ROOMS && chosenOfType < left;
                    return (
                      <li key={q.rate_plan.code} className={styles.plan}>
                        <div>
                          <strong>{q.rate_plan.name}</strong>
                          <span className={styles.planNote}>{q.rate_plan.description}</span>
                        </div>
                        {q.price ? (
                          <span className={styles.planPrice}>
                            {formatInr(q.price.total_paise)}
                            <span className={styles.planNote}>
                              1 room, {guestsLabel(q.price.lines[0]?.guests ?? 1)}, GST included
                            </span>
                          </span>
                        ) : (
                          <span className={styles.planNote}>Not on sale for these dates</span>
                        )}
                        {q.price &&
                          (line ? (
                            <LineControls
                              line={line}
                              maxGuestsPerRoom={room.max_guests}
                              canAddRoom={canAddRoom}
                              roomName={room.name}
                              onChange={(next) => update(room.code, q.rate_plan.code, () => next)}
                            />
                          ) : (
                            <button
                              type="button"
                              className="button-quiet"
                              disabled={!canAddRoom}
                              onClick={() => add(detail, q.rate_plan.code)}
                              aria-label={`Add ${room.name}, ${q.rate_plan.name}`}
                            >
                              Add
                            </button>
                          ))}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      {lines.length > 0 && (
        // On a phone the summary is far below; this bar keeps the total in view.
        <a href="#summary-title" className={styles.phoneBar}>
          <span>
            {totalRooms} {totalRooms === 1 ? "room" : "rooms"}
            {quote.state === "ready" && quote.key === key ? `, ${formatInr(quote.price.total_paise)}` : ""}
          </span>
          <span className={styles.phoneBarAction}>Review your stay</span>
        </a>
      )}

      <aside className={styles.summary} aria-labelledby="summary-title" aria-live="polite">
        <h2 id="summary-title">Your stay</h2>
        <p className={styles.stay}>
          {stayLabel(search.checkIn, search.checkOut)}, {guestsLabel(search.guests)}
        </p>
        {lines.length === 0 ? (
          <p className="muted">Add the rooms you want. You can mix room types, up to {MAX_ROOMS} rooms.</p>
        ) : (
          <>
            <ul className={styles.chosen}>
              {lines.map((l) => {
                const detail = byCode.get(l.roomType);
                const plan = detail?.rate_plans.find((p) => p.code === l.ratePlan);
                return (
                  <li key={`${l.roomType}.${l.ratePlan}`}>
                    {l.units} x {detail?.room.name ?? l.roomType}, {plan?.name ?? l.ratePlan}, {guestsLabel(l.guests)}
                  </li>
                );
              })}
            </ul>
            {totalGuests < search.guests && (
              <p className={styles.warn}>
                These rooms are for {guestsLabel(totalGuests)}; you searched for {search.guests}.
              </p>
            )}
            {(quote.state === "idle" || quote.key !== key) && <p className="muted">Working out the price.</p>}
            {quote.state === "error" && quote.key === key && (
              <p className={styles.warn} role="alert">
                {quote.message}
              </p>
            )}
            <form
              className={styles.promo}
              onSubmit={(e) => {
                e.preventDefault();
                const code = promoDraft.trim().toUpperCase();
                setPromoError(null);
                setPromo(code || null);
              }}
            >
              <label htmlFor="promo-code">Promo code</label>
              <div className={styles.promoRow}>
                <input
                  id="promo-code"
                  value={promoDraft}
                  maxLength={32}
                  autoComplete="off"
                  aria-invalid={promoError ? true : undefined}
                  aria-describedby={promoError ? "promo-error" : undefined}
                  onChange={(e) => setPromoDraft(e.target.value)}
                />
                <button type="submit" className="button-quiet">
                  Apply
                </button>
              </div>
              {promo && !promoError && <span className={styles.promoOk}>{promo} applied</span>}
              {promoError && (
                <span id="promo-error" className={styles.warn} role="alert">
                  {promoError}
                </span>
              )}
            </form>
            {quote.state === "ready" && quote.key === key && (
              <>
                <PriceBreakdown price={quote.price} />
                <BookButton
                  search={search}
                  lines={lines}
                  promoCode={promo}
                  onPromoError={(message) => {
                    setPromoError(message);
                    setPromo(null);
                  }}
                />
              </>
            )}
          </>
        )}
        {totalRooms >= MAX_ROOMS && <p className="muted">That is the most rooms for one booking ({MAX_ROOMS}).</p>}
      </aside>
    </div>
  );
}

function LineControls({
  line,
  maxGuestsPerRoom,
  canAddRoom,
  roomName,
  onChange,
}: {
  line: Line;
  maxGuestsPerRoom: number;
  canAddRoom: boolean;
  roomName: string;
  onChange: (next: Line | null) => void;
}) {
  const maxGuests = line.units * maxGuestsPerRoom;
  const setUnits = (units: number) =>
    onChange(units < 1 ? null : { ...line, units, guests: Math.min(Math.max(line.guests, units), units * maxGuestsPerRoom) });
  return (
    <div className={styles.controls}>
      <div className={styles.stepper} role="group" aria-label={`Rooms of ${roomName}`}>
        <button type="button" onClick={() => setUnits(line.units - 1)} aria-label="One room fewer">
          -
        </button>
        <span>
          {line.units} {line.units === 1 ? "room" : "rooms"}
        </span>
        <button type="button" onClick={() => setUnits(line.units + 1)} disabled={!canAddRoom} aria-label="One room more">
          +
        </button>
      </div>
      <label className={styles.guests}>
        Guests
        <input
          type="number"
          min={line.units}
          max={maxGuests}
          value={line.guests}
          onChange={(e) => {
            const g = Number(e.target.value) || line.units;
            onChange({ ...line, guests: Math.min(maxGuests, Math.max(line.units, g)) });
          }}
        />
      </label>
      <button type="button" className={styles.remove} onClick={() => onChange(null)}>
        Remove
      </button>
    </div>
  );
}
