import { formatInr } from "@/lib/format";
import type { PriceOut } from "@/lib/types";
import styles from "./PriceBreakdown.module.css";

/** Every figure comes from the backend's quote, in paise (A-166). Nothing is added up here. */
export function PriceBreakdown({ price }: { price: PriceOut }) {
  return (
    <dl className={styles.list}>
      <div>
        <dt>Room charges</dt>
        <dd>{formatInr(price.subtotal_paise)}</dd>
      </div>
      {price.discount_paise > 0 && (
        <div>
          <dt>{price.promo ? `Promo ${price.promo.code} (${price.promo.percent_off}% off)` : "Discount"}</dt>
          <dd>-{formatInr(price.discount_paise)}</dd>
        </div>
      )}
      <div>
        <dt>GST</dt>
        <dd>{formatInr(price.gst_paise)}</dd>
      </div>
      <div className={styles.total}>
        <dt>Total</dt>
        <dd>{formatInr(price.total_paise)}</dd>
      </div>
    </dl>
  );
}
