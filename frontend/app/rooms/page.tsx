import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";
import { SearchForm } from "@/components/SearchForm";
import { ApiError } from "@/lib/errors";
import { guestsLabel } from "@/lib/format";
import { roomPhotos } from "@/lib/photos";
import { serverGet } from "@/lib/server-api";
import { parseLines, parseSearch, searchQuery, type Search } from "@/lib/stay";
import type { RoomDetail, RoomSearch } from "@/lib/types";
import { RoomChooser } from "./RoomChooser";
import styles from "./rooms.module.css";

export const metadata: Metadata = { title: "Rooms and villas" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default function RoomsPage({ searchParams }: Props) {
  return (
    <div className={`page ${styles.wrap}`}>
      <h1>Rooms and villas</h1>
      <Suspense fallback={<p className="muted">Checking availability.</p>}>
        <Results searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Results({ searchParams }: Props) {
  const params = await searchParams;
  const search = parseSearch(params);
  const form = (
    <div className={styles.searchBox}>
      <SearchForm initial={search} compact />
    </div>
  );

  if (!search.checkIn || !search.checkOut) {
    return (
      <>
        {form}
        <p className="muted">Choose your dates to see prices and what is available.</p>
        <AllRooms search={search} />
      </>
    );
  }

  const dated = { ...search, checkIn: search.checkIn, checkOut: search.checkOut };
  let rooms: RoomDetail[];
  try {
    const list = await serverGet<RoomSearch>(`/api/rooms?${searchQuery(search)}`);
    // Each room's plans with a price for these dates (A-166: prices come from the API).
    rooms = await Promise.all(
      list.rooms.map((r) => serverGet<RoomDetail>(`/api/rooms/${r.code}?${searchQuery(search)}`)),
    );
  } catch (error) {
    return (
      <>
        {form}
        <p className={styles.empty} role="alert">
          {error instanceof ApiError && error.status === 422
            ? error.message
            : "Availability could not be checked right now. Please try again in a few minutes."}
        </p>
      </>
    );
  }

  const open = rooms.filter((r) => (r.room.available_units ?? 0) > 0);
  return (
    <>
      {form}
      {open.length === 0 && (
        <p className={styles.empty}>
          Everything is booked for these dates. Try other dates, or{" "}
          <Link href="/enquire">send us an enquiry</Link> and we will see what we can do.
        </p>
      )}
      <RoomChooser search={dated} rooms={rooms} initialLines={parseLines(params)} />
    </>
  );
}

async function AllRooms({ search }: { search: Search }) {
  let data: RoomSearch;
  try {
    data = await serverGet<RoomSearch>("/api/rooms");
  } catch {
    return <p className={styles.empty}>Room details could not be loaded. Refresh the page to try again.</p>;
  }
  return (
    <ul className={styles.results}>
      {data.rooms.map((room) => {
        const photo = roomPhotos(room.code)[0];
        return (
          <li key={room.code} className={styles.room}>
            {photo && (
              <div className={styles.thumb}>
                <Image src={photo.src} alt={photo.alt} fill placeholder="blur" sizes="(min-width: 48rem) 12rem, 100vw" />
              </div>
            )}
            <div className={styles.roomBody}>
              <div className={styles.roomHead}>
                <h2>
                  <Link href={`/rooms/${room.code}?${searchQuery(search)}`}>{room.name}</Link>
                </h2>
                <span className={styles.left}>For up to {guestsLabel(room.max_guests)}</span>
              </div>
              <p className={styles.description}>{room.description}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
