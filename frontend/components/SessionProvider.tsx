"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, loadSession, setCsrfToken } from "@/lib/api";
import type { Me } from "@/lib/types";

type Status = "loading" | "signed-in" | "signed-out" | "unavailable";

type SessionValue = {
  status: Status;
  me: Me | null;
  /** After login or sign-up: the account the API returned (carries the CSRF token). */
  signedIn: (me: Me) => void;
  logOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

/** Who is signed in, asked once per page load from GET /api/auth/me (D-49). */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);

  const apply = useCallback((account: Me | null | "unavailable") => {
    if (account === "unavailable") {
      setMe(null);
      setStatus("unavailable"); // the API could not be reached; pages say so
      return;
    }
    setMe(account);
    setStatus(account ? "signed-in" : "signed-out");
  }, []);

  const refresh = useCallback(async () => {
    apply(await loadSession().catch(() => "unavailable" as const));
  }, [apply]);

  useEffect(() => {
    // Ask once when the site loads; later changes come from signedIn and logOut.
    let current = true;
    loadSession()
      .catch(() => "unavailable" as const)
      .then((account) => {
        if (current) apply(account);
      });
    return () => {
      current = false;
    };
  }, [apply]);

  const signedIn = useCallback((account: Me) => {
    setCsrfToken(account.csrf_token);
    setMe(account);
    setStatus("signed-in");
  }, []);

  const logOut = useCallback(async () => {
    try {
      await api<void>("/api/auth/logout", { method: "POST" });
    } finally {
      setCsrfToken(null);
      setMe(null);
      setStatus("signed-out");
    }
  }, []);

  const value = useMemo(() => ({ status, me, signedIn, logOut, refresh }), [status, me, signedIn, logOut, refresh]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}

export function isStaff(me: Me | null): boolean {
  return me?.role === "staff";
}
