/** Plain words for the backend's payment statuses. */
export function paymentLabel(status: string): string {
  switch (status) {
    case "succeeded":
      return "Paid in full";
    case "refunded":
      return "Refunded in full";
    case "refund_pending":
      return "Full refund in progress";
    default:
      return status.replaceAll("_", " ");
  }
}

export function linesLabel(lines: { units: number; room_type_name: string; rate_plan_name: string; guests: number }[]) {
  return lines.map(
    (l) => `${l.units} x ${l.room_type_name}, ${l.rate_plan_name}, ${l.guests} ${l.guests === 1 ? "guest" : "guests"}`,
  );
}
