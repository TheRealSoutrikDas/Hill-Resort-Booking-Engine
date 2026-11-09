import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { SearchForm } from "@/components/SearchForm";
import { ApiError } from "@/lib/errors";
import { formatInr, guestsLabel } from "@/lib/format";
import { serverGet } from "@/lib/server-api";
import { parseSearch, searchQuery, stayLabel } from "@/lib/stay";
import type { RoomDetail } from "@/lib/types";
import styles from "../rooms.module.css";

export const metadata: Metadata = { title: "Room" };

type Props = {
  params: Promise<{ code: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default function RoomPage(props: Props) {
  return (
    <div className={`page ${styles.wrap}`}>
      <Suspense fallback={<p className="muted">Loading the room.</p>}>
        <Room {...props} />
      </Suspense>
    </div>
  );
}

async function Room({ params, searchParams }: Props) {
  const { code } = await params;
  const search = parseSearch(await searchParams);
  if (!/^[A-Za-z0-9_]{1,32}$/.test(code)) notFound();

  let detail: RoomDetail;
  try {
    detail = await serverGet<RoomDetail>(`/api/rooms/${encodeURIComponent(code)}?${searchQuery(search)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    const message =
      error instanceof ApiError && error.status === 422
        ? error.message
        : "This room could not be loaded right now. Please try again in a few minutes.";
    return (
      <>
        <p>
          <Link href={`/rooms?${searchQuery(search)}`}>All rooms and villas</Link>
        </p>
        <p className={styles.empty} role="alert">
          {message}
        </p>
        <SearchForm initial={search} compact />
      </>
    );
  }

  const room = detail.room;
  const dated = search.checkIn && search.checkOut;
  const left = room.available_units ?? 0;
  return (
    <>
      <p>
        <Link href={`/rooms?${searchQuery(search)}`}>All rooms and villas</Link>
      </p>
      <h1>{room.name}</h1>
      <p>
        {room.description} For up to {guestsLabel(room.max_guests)}.
      </p>
      <div className={styles.searchBox}>
        <SearchForm initial={search} compact />
      </div>
      {dated ? (
        <>
          <h2>
            {stayLabel(search.checkIn!, search.checkOut!)}
            {left === 0 ? "" : `, ${left} left`}
          </h2>
          {left === 0 && <p className={styles.soldOut}>Sold out for these dates. Try other dates.</p>}
          <ul className={styles.plans}>
            {(detail.quotes ?? []).map((q) => (
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
                {q.price && left > 0 && (
                  <Link
                    className="button-quiet"
                    href={`/rooms?${searchQuery(search, [
                      {
                        roomType: room.code,
                        ratePlan: q.rate_plan.code,
                        units: 1,
                        guests: Math.min(search.guests, room.max_guests),
                      },
                    ])}`}
                  >
                    Choose {q.rate_plan.name}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <h2>Rate plans</h2>
          <ul className={styles.plans}>
            {detail.rate_plans.map((p) => (
              <li key={p.code} className={styles.plan}>
                <div>
                  <strong>{p.name}</strong>
                  <span className={styles.planNote}>{p.description}</span>
                </div>
              </li>
            ))}
          </ul>
          <p className="muted">Choose your dates above to see prices.</p>
        </>
      )}
    </>
  );
}
