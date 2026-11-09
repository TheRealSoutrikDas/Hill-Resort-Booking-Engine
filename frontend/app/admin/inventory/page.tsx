import type { Metadata } from "next";
import { InventoryAdmin } from "./InventoryAdmin";

export const metadata: Metadata = { title: "Inventory" };

export default function InventoryPage() {
  return <InventoryAdmin />;
}
