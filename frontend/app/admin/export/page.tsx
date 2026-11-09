import type { Metadata } from "next";
import { ExportAdmin } from "./ExportAdmin";

export const metadata: Metadata = { title: "Daily export" };

export default function ExportPage() {
  return <ExportAdmin />;
}
