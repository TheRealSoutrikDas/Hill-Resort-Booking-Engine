import type { Metadata } from "next";
import { Alerts } from "./Alerts";

export const metadata: Metadata = { title: "GM alerts" };

export default function AlertsPage() {
  return <Alerts />;
}
