import type { Metadata } from "next";
import { Metrics } from "./Metrics";

export const metadata: Metadata = { title: "Metrics" };

export default function MetricsPage() {
  return <Metrics />;
}
