"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { atIndia, laneLabel } from "@/lib/lanes";
import type { AlertItem, AlertList } from "@/lib/types";
import styles from "../staff.module.css";

/** Complaints alert the GM whatever the AI says (brief). Only the GM acknowledges (A-190). */
export function Alerts() {
  const { me } = useSession();
  const [data, setData] = useState<AlertList | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    api<AlertList>("/api/alerts")
      .then((d) => current && setData(d))
      .catch(() => current && setProblem("Alerts could not be loaded. Use Refresh to try again."));
    return () => {
      current = false;
    };
  }, [version]);

  return (
    <>
      <div className={styles.head}>
        <h1>GM alerts</h1>
        <button type="button" className="button-quiet" onClick={() => setVersion((v) => v + 1)}>
          Refresh
        </button>
      </div>
      {data && (
        <p className="muted">
          {data.open === 0 ? "No open alerts." : `${data.open} open ${data.open === 1 ? "alert" : "alerts"}.`}{" "}
          {me?.is_gm ? "" : "Only the GM can acknowledge alerts."}
        </p>
      )}
      {problem && (
        <FormAlert>
          <p>{problem}</p>
        </FormAlert>
      )}
      {!data && !problem && <p className="muted">Loading alerts.</p>}
      {data && data.items.length === 0 && <p className={styles.note}>No complaints have raised an alert.</p>}
      {data && data.items.length > 0 && (
        <ul className={styles.list}>
          {data.items.map((a) => (
            <AlertRow key={a.id} alert={a} canAck={!!me?.is_gm} onDone={() => setVersion((v) => v + 1)} />
          ))}
        </ul>
      )}
    </>
  );
}

function AlertRow({ alert, canAck, onDone }: { alert: AlertItem; canAck: boolean; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <li className={styles.row}>
      <div className={styles.rowHead}>
        <Link href={`/staff/enquiries/${alert.reference}`} className={styles.reference}>
          {alert.reference}
        </Link>
        {!alert.acknowledged_at && <span className={`${styles.badge} ${styles.alertBadge}`}>Open</span>}
        <span className={styles.meta}>
          {atIndia(alert.created_at)}, {alert.reason}, now in {laneLabel(alert.lane)}
        </span>
      </div>
      {alert.acknowledged_at ? (
        <p className={styles.meta}>
          Acknowledged by {alert.acknowledged_by} on {atIndia(alert.acknowledged_at)}
        </p>
      ) : (
        canAck && (
          <div className={styles.actions}>
            <button
              type="button"
              className="button-quiet"
              disabled={busy}
              aria-label={`Acknowledge alert for ${alert.reference}`}
              onClick={async () => {
                setBusy(true);
                setProblem(null);
                try {
                  await api(`/api/alerts/${alert.id}/ack`, { method: "POST" });
                  onDone();
                } catch (error) {
                  setProblem(error instanceof ApiError ? error.message : "Could not acknowledge.");
                  setBusy(false);
                }
              }}
            >
              {busy ? "Acknowledging" : "Acknowledge"}
            </button>
          </div>
        )
      )}
      {problem && <p role="alert">{problem}</p>}
    </li>
  );
}
