import Image from "next/image";
import type { Photo } from "@/lib/photos";
import styles from "./PhotoPanel.module.css";

/** A form page with a photo beside it on wide screens. On a phone the photo is left
 * out, so the form comes first. The photo is decorative and not a link (A-196). */
export function PhotoPanel({ photo, children }: { photo: Photo; children: React.ReactNode }) {
  return (
    <div className={`page ${styles.split}`}>
      <div className={styles.content}>{children}</div>
      <div className={styles.panel}>
        <Image src={photo.src} alt={photo.alt} fill placeholder="blur" sizes="(min-width: 64rem) 40vw, 1px" />
      </div>
    </div>
  );
}
