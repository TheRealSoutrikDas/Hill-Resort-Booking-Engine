import Image from "next/image";
import Link from "next/link";
import { NOT_FOUND } from "@/lib/photos";
import styles from "./not-found.module.css";

export default function NotFound() {
  return (
    <div className={`page ${styles.wrap}`}>
      <div className={styles.photo}>
        <Image src={NOT_FOUND.src} alt={NOT_FOUND.alt} fill placeholder="blur" sizes="(min-width: 72rem) 68rem, 100vw" />
      </div>
      <h1>Page not found</h1>
      <p>The address may be mistyped, or the page may have moved.</p>
      <p>
        <Link href="/">Go to the home page</Link>
      </p>
    </div>
  );
}
