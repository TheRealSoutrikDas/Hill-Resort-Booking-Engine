import { Suspense } from "react";
import { EstateHills } from "@/components/EstateHills";
import { RoomList, RoomListSkeleton } from "@/components/RoomList";
import { SearchForm } from "@/components/SearchForm";
import styles from "./page.module.css";

export default function Home() {
  return (
    <>
      <section className={styles.hero}>
        <div className={`page ${styles.heroText}`}>
          <h1>Stay among the coffee in Chikkamagaluru</h1>
          <p className={styles.lede}>
            CompanyA is a coffee-estate resort in the hills of Karnataka, with 64 rooms and 12 villas.
            Book directly with us.
          </p>
        </div>
        <EstateHills className={styles.hills} />
      </section>

      <section className={`page ${styles.search}`} aria-label="Check availability">
        <SearchForm />
      </section>

      <section id="rooms" className={`page ${styles.section}`} aria-labelledby="rooms-title">
        <h2 id="rooms-title">Rooms and villas</h2>
        <p className="muted">Prices depend on your dates and are shown with GST included.</p>
        <Suspense fallback={<RoomListSkeleton />}>
          <RoomList />
        </Suspense>
      </section>

      <section id="visit" className={`page ${styles.section}`} aria-labelledby="visit-title">
        <h2 id="visit-title">Visit</h2>
        <p>CompanyA, Chikkamagaluru, Karnataka, India.</p>
      </section>
    </>
  );
}
