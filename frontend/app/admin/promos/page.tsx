import type { Metadata } from "next";
import { PromosAdmin } from "./PromosAdmin";

export const metadata: Metadata = { title: "Promo codes" };

export default function PromosPage() {
  return <PromosAdmin />;
}
