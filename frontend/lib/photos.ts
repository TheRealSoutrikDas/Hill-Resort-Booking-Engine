import type { StaticImageData } from "next/image";
import cup from "@/public/images/estate-cup.jpg";
import cherries from "@/public/images/estate-cherries.jpg";
import rows from "@/public/images/estate-rows.jpg";
import hero from "@/public/images/hero.jpg";
import notFound from "@/public/images/not-found.jpg";
import panelAccount from "@/public/images/panel-account.jpg";
import panelEnquire from "@/public/images/panel-enquire.jpg";
import dlx1 from "@/public/images/rooms/DLX-1.jpg";
import dlx2 from "@/public/images/rooms/DLX-2.jpg";
import dlx3 from "@/public/images/rooms/DLX-3.jpg";
import evr1 from "@/public/images/rooms/EVR-1.jpg";
import evr2 from "@/public/images/rooms/EVR-2.jpg";
import evr3 from "@/public/images/rooms/EVR-3.jpg";
import fst1 from "@/public/images/rooms/FST-1.jpg";
import fst2 from "@/public/images/rooms/FST-2.jpg";
import fst3 from "@/public/images/rooms/FST-3.jpg";
import plv2 from "@/public/images/rooms/PLV-2.jpg";
import plv3 from "@/public/images/rooms/PLV-3.jpg";
import ppv1 from "@/public/images/rooms/PPV-1.jpg";
import ppv2 from "@/public/images/rooms/PPV-2.jpg";
import ppv3 from "@/public/images/rooms/PPV-3.jpg";

/** A sample photo (A-157, A-193). `alt` says what the photo shows, never that it is
 * CompanyA; an empty `alt` marks a purely decorative photo (A-196). Sources and
 * licences are in docs/PHOTO_SOURCES.md. */
export type Photo = { src: StaticImageData; alt: string };

export const HERO: Photo = { src: hero, alt: "Coffee plantation under shade trees in morning fog" };

export const ESTATE: Photo[] = [
  { src: rows, alt: "Rows of coffee plants on a hillside" },
  { src: cherries, alt: "Ripe coffee cherries on the branch" },
  { src: cup, alt: "A hand picking ripe coffee cherries from the branch" },
];

// Decorative: the page beside them says everything.
export const PANEL_ACCOUNT: Photo = { src: panelAccount, alt: "" };
export const PANEL_ENQUIRE: Photo = { src: panelEnquire, alt: "" };
export const NOT_FOUND: Photo = { src: notFound, alt: "" };

/** Photos per room type, by room code (A-88, A-198). The first is the main one. A room
 * type without photos here simply shows none. */
const ROOM_PHOTOS: Record<string, Photo[]> = {
  DLX: [
    { src: dlx1, alt: "Bedroom with a large bed and a garden view" },
    { src: dlx2, alt: "Room with a bed, a chair and a window" },
    { src: dlx3, alt: "Leafy plant beside a bed" },
  ],
  EVR: [
    { src: evr1, alt: "Room with a large window looking out on trees" },
    { src: evr2, alt: "Bedroom with a large bed, an armchair and a ceiling fan" },
    { src: evr3, alt: "Green hillside with hills behind" },
  ],
  FST: [
    { src: fst1, alt: "Cushioned seat on a balcony with plants" },
    { src: fst2, alt: "White bed and floor lamp in morning sun" },
    { src: fst3, alt: "Wooden bed frame with white linen" },
  ],
  PLV: [
    { src: plv2, alt: "Wooden chairs and a table on a porch" },
    { src: plv3, alt: "Wooden deck rail among leafy plants" },
    { src: rows, alt: "Rows of coffee plants on a hillside" },
  ],
  PPV: [
    { src: ppv1, alt: "Pool in front of a villa among tropical plants" },
    { src: ppv2, alt: "Pool surrounded by trees, seen from above" },
    { src: ppv3, alt: "Wooden dining table and chairs" },
  ],
};

export function roomPhotos(code: string): Photo[] {
  return ROOM_PHOTOS[code] ?? [];
}
