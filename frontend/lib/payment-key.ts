// One Idempotency-Key per payment attempt, kept for the hold until the attempt has a
// final answer (A-168). A double click or a reload sends the same key, so the backend
// returns the first attempt's result instead of charging again. sessionStorage is per
// tab and can be unavailable (private mode), so a copy is also kept in memory.
const memory = new Map<string, string>();
const name = (holdId: string) => `payment-key:${holdId}`;

export function paymentKey(holdId: string): string {
  let key = memory.get(holdId) ?? null;
  try {
    key = key ?? window.sessionStorage.getItem(name(holdId));
  } catch {
    /* storage unavailable: memory only */
  }
  if (!key) key = crypto.randomUUID();
  memory.set(holdId, key);
  try {
    window.sessionStorage.setItem(name(holdId), key);
  } catch {
    /* ignore */
  }
  return key;
}

/** After a final answer (confirmed, declined, timed out): the next attempt gets a new key. */
export function forgetPaymentKey(holdId: string): void {
  memory.delete(holdId);
  try {
    window.sessionStorage.removeItem(name(holdId));
  } catch {
    /* ignore */
  }
}
