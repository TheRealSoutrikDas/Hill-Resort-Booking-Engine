import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";
import { EstateHills } from "@/components/EstateHills";
import { RoomList, RoomListSkeleton } from "@/components/RoomList";
import { SearchForm } from "@/components/SearchForm";
import { ESTATE, HERO } from "@/lib/photos";
import styles from "./page.module.css";

export default function Home() {
  const [rows, cherries, cup] = ESTATE;
  return (
    <>
      <section className={styles.hero}>
        <Image
          src={HERO.src}
          alt={HERO.alt}
          fill
          priority
          placeholder="blur"
          sizes="100vw"
          className={styles.heroPhoto}
        />
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

      <section id="estate" className={`page ${styles.section}`} aria-labelledby="estate-title">
        <div className={styles.estate}>
          <div className={styles.estateText}>
            <h2 id="estate-title">On a coffee estate</h2>
            <p>
              The rooms and villas sit among the coffee on the hillsides of Chikkamagaluru, in
              Karnataka. Stay with breakfast or the room alone, and for weddings, company offsites
              and group stays, send us an enquiry.
            </p>
          </div>
          <figure className={`${styles.figure} ${styles.figureTall}`}>
            <div className={styles.frame}>
              <Image src={rows.src} alt={rows.alt} fill placeholder="blur" sizes="(min-width: 64rem) 34rem, 100vw" />
            </div>
          </figure>
          <figure className={styles.figure}>
            <div className={styles.frame}>
              <Image src={cherries.src} alt={cherries.alt} fill placeholder="blur" sizes="(min-width: 64rem) 22rem, 50vw" />
            </div>
          </figure>
          <figure className={styles.figure}>
            <div className={styles.frame}>
              <Image src={cup.src} alt={cup.alt} fill placeholder="blur" sizes="(min-width: 64rem) 22rem, 50vw" />
            </div>
          </figure>
        </div>
      </section>

      <section id="visit" className={`page ${styles.section}`} aria-labelledby="visit-title">
        <h2 id="visit-title">Visit</h2>
        <p>CompanyA, Chikkamagaluru, Karnataka, India.</p>
        <p>
          Planning a wedding, a company offsite or a group stay, or have a question?{" "}
          <Link href="/enquire">Send us an enquiry</Link> and our team will reply.
        </p>
      </section>
    </>
  );
}
