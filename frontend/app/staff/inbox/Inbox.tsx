"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { FormAlert } from "@/components/forms/Field";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { LANES, STATUSES, TEAMS, atIndia, homeLane, laneLabel } from "@/lib/lanes";
import type { InboxOut } from "@/lib/types";
import styles from "../staff.module.css";

const TAB_KEYS: string[] = [...LANES.map((l) => l.key), ...STATUSES.map((s) => s.key)];

export function Inbox() {
  const { me } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const requested = params.get("tab");
  const tab = requested && TAB_KEYS.includes(requested) ? requested : homeLane(me); // A-186
  const isStatus = STATUSES.some((s) => s.key === tab);
  const [data, setData] = useState<{ tab: string; inbox: InboxOut } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    api<InboxOut>(`/api/enquiries?${isStatus ? "status" : "lane"}=${tab}`)
      .then((inbox) => {
        if (!current) return;
        setData({ tab, inbox });
        setProblem(null);
      })
      .catch(() => current && setProblem("The inbox could not be loaded. Use Refresh to try again."));
    return () => {
      current = false;
    };
  }, [tab, isStatus, version]);

  const counts = data?.inbox.counts ?? {};
  const items = data?.tab === tab ? data.inbox.items : null;
  const open = (key: string) => router.replace(`/staff/inbox?tab=${key}`, { scroll: false });

  return (
    <>
      <div className={styles.head}>
        <h1>Inbox</h1>
        {/* A-191: refresh on demand; no polling. */}
        <button type="button" className="button-quiet" onClick={() => setVersion((v) => v + 1)}>
          Refresh
        </button>
      </div>
      <div className={styles.tabs} role="tablist" aria-label="Lanes">
        {LANES.map((l) => (
          <Tab key={l.key} id={l.key} label={l.label} count={counts[l.key]} selected={tab === l.key} onSelect={open} />
        ))}
        <span className={styles.tabGap} aria-hidden="true" />
        {STATUSES.map((s) => (
          <Tab key={s.key} id={s.key} label={s.label} count={counts[s.key]} selected={tab === s.key} onSelect={open} />
        ))}
      </div>
      <div role="tabpanel" id="inbox-panel" aria-labelledby={`tab-${tab}`}>
        {problem && (
          <FormAlert>
            <p>{problem}</p>
          </FormAlert>
        )}
        {!items && !problem && <p className="muted">Loading enquiries.</p>}
        {items && items.length === 0 && <p className={styles.note}>Nothing here right now.</p>}
        {items && items.length > 0 && (
          <ul className={styles.list}>
            {items.map((e) => (
              <li key={e.reference} className={styles.row}>
                <div className={styles.rowHead}>
                  <Link href={`/staff/enquiries/${e.reference}`} className={styles.reference}>
                    {e.reference}
                  </Link>
                  <span>{e.contact_name}</span>
                  <span className={styles.meta}>
                    {atIndia(e.received_at)}, by {e.channel}
                  </span>
                  {e.gm_alert && <span className={`${styles.badge} ${styles.alertBadge}`}>GM alert</span>}
                  {e.is_fallback && <span className={styles.badge}>Keyword fallback</span>}
                  {isStatus && <span className={styles.badge}>{laneLabel(e.lane)}</span>}
                  {e.owner_team && <span className={styles.meta}>{TEAMS[e.owner_team] ?? e.owner_team}</span>}
                </div>
                <p>{e.snippet}</p>
              </li>
            ))}
          </ul>
        )}
        {items && items.length >= 200 && <p className="muted">Showing the newest 200.</p>}
      </div>
    </>
  );
}

function Tab({
  id,
  label,
  count,
  selected,
  onSelect,
}: {
  id: string;
  label: string;
  count: number | undefined;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      id={`tab-${id}`}
      aria-selected={selected}
      aria-controls="inbox-panel"
      className={styles.tab}
      onClick={() => onSelect(id)}
    >
      {label} <span className={styles.count}>{count ?? ""}</span>
    </button>
  );
}
