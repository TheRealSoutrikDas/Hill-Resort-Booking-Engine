// Types generated from the backend's OpenAPI schema (A-153). Regenerate with
// `npm run api:types` after `python -m app.export_openapi > ../frontend/lib/openapi.json`.
import type { components } from "./api-schema";

export type Schemas = components["schemas"];
export type ErrorResponse = Schemas["ErrorResponse"];
export type RoomSearch = Schemas["RoomSearch"];
export type RoomSummary = Schemas["RoomSummary"];
export type Me = Schemas["Me"];
export type RoomDetail = Schemas["RoomDetail"];
export type PlanQuote = Schemas["PlanQuote"];
export type PriceOut = Schemas["PriceOut"];
export type StayIn = Schemas["StayIn"];
export type HoldOut = Schemas["HoldOut"];
export type PaymentOut = Schemas["PaymentOut"];
export type BookingOut = Schemas["BookingOut"];
export type GuestDetails = Schemas["GuestDetails"];
export type MyBooking = Schemas["MyBooking"];
export type LookupOut = Schemas["LookupOut"];
export type Inventory = Schemas["Inventory"];
export type RoomTypeInventory = Schemas["RoomTypeInventory"];
export type AdminPromo = Schemas["app__api__admin_promos__PromoOut"];
export type InboxOut = Schemas["Inbox"];
export type InboxItem = Schemas["InboxItem"];
export type EnquiryDetail = Schemas["EnquiryDetail"];
export type HistoryEntry = Schemas["HistoryEntry"];
export type AlertList = Schemas["AlertList"];
export type AlertItem = Schemas["AlertItem"];
export type MetricsOut = Schemas["MetricsOut"];
export type RateOut = Schemas["RateOut"];
