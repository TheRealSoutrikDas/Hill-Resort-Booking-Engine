"use client";

import { api } from "./api";
import type { RoomDetail, RoomSearch } from "./types";

export type Names = { rooms: Map<string, string>; plans: Map<string, string> };

/** Room and plan names for codes in a hold or booking (the API returns codes there). */
export async function loadNames(): Promise<Names> {
  const list = await api<RoomSearch>("/api/rooms");
  const rooms = new Map(list.rooms.map((r) => [r.code, r.name]));
  const plans = new Map<string, string>();
  if (list.rooms[0]) {
    // Rate plans are the same for every room type.
    const detail = await api<RoomDetail>(`/api/rooms/${list.rooms[0].code}`);
    for (const p of detail.rate_plans) plans.set(p.code, p.name);
  }
  return { rooms, plans };
}

export function lineLabel(
  names: Names | null,
  line: { room_type: string; rate_plan: string; units: number; guests: number },
): string {
  const room = names?.rooms.get(line.room_type) ?? line.room_type;
  const plan = names?.plans.get(line.rate_plan) ?? line.rate_plan;
  return `${line.units} x ${room}, ${plan}, ${line.guests} ${line.guests === 1 ? "guest" : "guests"}`;
}
