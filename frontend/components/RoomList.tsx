import Image from "next/image";
import Link from "next/link";
import { ApiError } from "@/lib/errors";
import { guestsLabel } from "@/lib/format";
import { roomPhotos } from "@/lib/photos";
import { serverGet } from "@/lib/server-api";
import type { RoomSearch } from "@/lib/types";
import styles from "./RoomList.module.css";

const KIND_LABEL: Record<string, string> = { room: "Room", villa: "Villa" };

/** Room types from GET /api/rooms. Prices need dates, so they come on the room pages. */
export async function RoomList() {
  let data: RoomSearch;
  try {
    data = await serverGet<RoomSearch>("/api/rooms");
  } catch (error) {
    const reference = error instanceof ApiError && error.requestId ? ` (reference ${error.requestId})` : "";
    return (
      <div className={styles.problem} role="alert">
        <p>
          Room details could not be loaded{reference}. Refresh the page to try again, or come back in a
          few minutes.
        </p>
      </div>
    );
  }
  if (data.rooms.length === 0) {
    return <p className={styles.problem}>No rooms are open for booking at the moment.</p>;
  }
  return (
    <ul className={styles.list}>
      {data.rooms.map((room) => {
        const photo = roomPhotos(room.code)[0];
        return (
          <li key={room.code} className={styles.item}>
            {photo && (
              <div className={styles.photo}>
                <Image
                  src={photo.src}
                  alt={photo.alt}
                  fill
                  placeholder="blur"
                  sizes="(min-width: 48rem) 40vw, 100vw"
                />
              </div>
            )}
            <div className={styles.text}>
              <h3>
                <Link href={`/rooms/${room.code}`}>{room.name}</Link>
              </h3>
              <p className={styles.meta}>
                {KIND_LABEL[room.kind] ?? room.kind}, for up to {guestsLabel(room.max_guests)}
              </p>
              <p className={styles.description}>{room.description}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function RoomListSkeleton() {
  return (
    <ul className={styles.list} aria-busy="true" aria-label="Loading rooms">
      {[0, 1, 2].map((i) => (
        <li key={i} className={`${styles.item} ${styles.skeleton}`}>
          <span className={styles.bar} style={{ width: "40%" }} />
          <span className={styles.bar} style={{ width: "85%" }} />
        </li>
      ))}
    </ul>
  );
}
