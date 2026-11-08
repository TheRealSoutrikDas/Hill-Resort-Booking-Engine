// Types generated from the backend's OpenAPI schema (A-153). Regenerate with
// `npm run api:types` after `python -m app.export_openapi > ../frontend/lib/openapi.json`.
import type { components } from "./api-schema";

export type Schemas = components["schemas"];
export type ErrorResponse = Schemas["ErrorResponse"];
export type RoomSearch = Schemas["RoomSearch"];
export type RoomSummary = Schemas["RoomSummary"];
export type Me = Schemas["Me"];
