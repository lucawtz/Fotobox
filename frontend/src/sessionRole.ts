import { useEffect, useState } from "react";
import { api, AdminRole } from "./api";

/** `undefined` = Rolle steht noch nicht fest, `null` = nicht eingeloggt. */
export type MaybeRole = AdminRole | null | undefined;

// Einmal pro Seitenaufruf abfragen und teilen: Galerie, Detailansicht und
// Loesch-Dialog wuerden sonst jeder fuer sich /api/admin/me rufen — auf einem
// ausgelasteten Hotspot drei ueberfluessige Roundtrips.
let cached: Promise<AdminRole | null> | null = null;

export function sessionRole(): Promise<AdminRole | null> {
  if (!cached) {
    cached = api.admin
      .me()
      .then((r) => (r.authenticated ? r.role : null))
      .catch(() => null);   // Netzfehler = wie ausgeloggt behandeln
  }
  return cached;
}

/** Nach Login/Logout aufrufen, sonst sitzt die Galerie auf der alten Rolle. */
export function clearSessionRole(): void {
  cached = null;
}

export function useSessionRole(): MaybeRole {
  const [role, setRole] = useState<MaybeRole>(undefined);
  useEffect(() => {
    let alive = true;
    sessionRole().then((r) => { if (alive) setRole(r); });
    return () => { alive = false; };
  }, []);
  return role;
}
