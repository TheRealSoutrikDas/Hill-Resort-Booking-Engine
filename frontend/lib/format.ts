const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const inrPaise = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

/** Money is integer paise everywhere (brief). Whole rupees are shown without decimals. */
export function formatInr(paise: number): string {
  return paise % 100 === 0 ? inr.format(paise / 100) : inrPaise.format(paise / 100);
}

export function guestsLabel(n: number): string {
  return n === 1 ? "1 guest" : `${n} guests`;
}
