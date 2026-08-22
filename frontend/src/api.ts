/** Was fuer ein Bild das ist — vom Server aus dem Dateinamen abgeleitet,
 *  siehe collage.classify(). */
export type PhotoKind = "collage" | "member" | "single";

export interface Photo {
  event: string;
  filename: string;
  mtime: number;
  size: number;
  kind: PhotoKind;
  /** Verbindet eine Collage mit den vier Aufnahmen, aus denen sie besteht.
   *  null bei eigenstaendigen Einzelfotos. */
  group: string | null;
}

/** Was die Galerie zeigt. "alle" faltet die vier Aufnahmen einer Collage in
 *  diese hinein — sonst stuende jede Collage funffach in der Uebersicht. */
export type PhotoFilter = "alle" | "collage" | "single";

export const matchesFilter = (p: Photo, f: PhotoFilter): boolean => {
  if (f === "collage") return p.kind === "collage";
  // Einzelbilder schliesst die Aufnahmen einer Collage bewusst mit ein: der
  // Gast soll auch an seine Rohbilder kommen, nicht nur an die Montage.
  if (f === "single") return p.kind === "single" || p.kind === "member";
  return p.kind !== "member";
};

/** Instagram-/Booking-Link des Box-Besitzers. Leerer String = nicht
 *  konfiguriert, dann blendet <OwnerLinks> den jeweiligen Button aus. */
export interface OwnerLinks {
  instagram_url: string;
  booking_url: string;
  booking_label: string;
}

export interface PhotosResponse extends OwnerLinks {
  event_name: string;
  active_event: string;
  filter: string | null;
  count: number;
  photos: Photo[];
  photo_max_age_days: number;
}

export interface EventInfo {
  folder:  string;
  date:    string;
  slug:    string;
  display: string;
  count:   number;
  mtime:   number;
  cover:   string;
  active:  boolean;
}

export interface EventsResponse extends OwnerLinks {
  active: string;
  event_name: string;
  events: EventInfo[];
  photo_max_age_days: number;
}

export const photoKey = (p: Pick<Photo, "event" | "filename">) =>
  `${p.event}/${p.filename}`;

export const formatDate = (iso: string): string => {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", {
    day: "numeric", month: "long", year: "numeric",
  });
};

/** Was bei der Uebergabe an den naechsten Gastgeber zurueckgesetzt wird.
 *  WLAN und PINs fehlen bewusst — die vergibt der Box-Besitzer selbst. */
export interface HandoverSteps {
  branding:  boolean;
  logo:      boolean;
  photos:    boolean;
  new_event: boolean;
}

export interface HandoverResult {
  ok: boolean;
  error?: string;
  done: HandoverSteps;
  removed: number;
  /** Ordner des frisch gestarteten Events, null wenn nicht angehakt. */
  folder: string | null;
}

export interface DeleteResult {
  ok: boolean;
  error?: string;
  removed?: number;
}

export type AdminRole = "admin" | "host";

export type ThemeColors = Record<string, string | number>;

export interface AdminConfig {
  event_name: string;
  subtitle: string;
  countdown_duration: number;
  has_logo: boolean;
  role: AdminRole;
  theme: ThemeColors;
  instagram_url: string;
  booking_url: string;
  insecure_defaults?: string[];
  print_enabled: boolean;
  printer_name: string;
  print_copies: number;
  print_mode: "auto" | "cover" | "fit";
  // Nur Admin sieht diese Felder — Gastgeber bekommt sie nicht vom Server.
  wifi_ssid?: string;
  wifi_password?: string;
  admin_pin?: string;
  host_pin?: string;
}

export interface Printer {
  name: string;
  state: string;
  ready: boolean;
  line: string;
}

export interface PrinterInfo {
  ok: boolean;
  error?: string;
  printers: Printer[];
  default: string | null;
  status: { available: boolean; printer: string | null; message: string };
}

export interface AdminStatus {
  camera_ok: boolean;
  free_mb: number;
  free_gb: number;
  total_mb: number;
  total_gb: number;
  photo_count: number;
  event_name: string;
}

const FETCH_OPTS: RequestInit = { credentials: "include" };

// Auf einem ausgelasteten 2,4-GHz-Hotspot (hotspot.py pinnt Band bg / Kanal 6)
// bleibt eine Anfrage sonst endlos haengen und der Spinner dreht sich fuer
// immer. Lieber ein klarer Fehler, den der Gast durch Neuladen loest.
const TIMEOUT_MS = 12_000;
const UPLOAD_TIMEOUT_MS = 60_000;   // Logo-Upload darf laenger brauchen

/** fetch mit Zeitlimit. AbortController statt AbortSignal.timeout(), damit
 *  auch aeltere Handy-Browser (Safari < 16) mitspielen. */
const xfetch = async (url: string, opts: RequestInit = {},
                      timeoutMs: number = TIMEOUT_MS): Promise<Response> => {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...FETCH_OPTS, ...opts, signal: ctl.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("Zeitüberschreitung — WLAN überlastet? Bitte neu laden.");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
};

const json = async <T,>(res: Response): Promise<T> => {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j?.error) msg = j.error; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
};

const postJson = (url: string, body: unknown) => xfetch(url, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const evPath = (p: Pick<Photo, "event" | "filename">) =>
  `${encodeURIComponent(p.event)}/${encodeURIComponent(p.filename)}`;

export const api = {
  list: (event?: string | null) =>
    xfetch("/api/photos" + (event ? `?event=${encodeURIComponent(event)}` : ""))
      .then(json<PhotosResponse>),
  count: (event?: string | null) =>
    xfetch("/api/count" + (event ? `?event=${encodeURIComponent(event)}` : ""))
      .then(json<{ count: number }>),
  events: () => xfetch("/api/events").then(json<EventsResponse>),

  thumbUrl:    (p: Pick<Photo, "event" | "filename">) => `/thumb/${evPath(p)}`,
  // Preview = 1280px JPEG mit Quality 80 — viel schneller über Hotspot als
  // Original. Nur Download und Originalansicht nutzen imgUrl.
  previewUrl:  (p: Pick<Photo, "event" | "filename">) => `/preview/${evPath(p)}`,
  imgUrl:      (p: Pick<Photo, "event" | "filename">) => `/img/${evPath(p)}`,
  downloadUrl: (p: Pick<Photo, "event" | "filename">) => `/download/${evPath(p)}`,
  // kind nur mitschicken, wenn wirklich gefiltert wird — ohne den Parameter
  // packt der Server bewusst das komplette Event ein.
  zipUrl:      (event?: string | null, kind?: PhotoFilter) => {
    if (!event) return "/api/download-zip";
    const q = new URLSearchParams({ event });
    if (kind && kind !== "alle") q.set("kind", kind);
    return `/api/download-zip?${q.toString()}`;
  },
  logoUrl:     () => `/api/admin/logo/preview?t=${Date.now()}`,
  // Nie direkt auf instagram_url/booking_url verlinken: der Gast steckt beim
  // Betrachten der Galerie per Definition im Fotobox-WLAN, und dort biegt der
  // Captive-DNS jede Domain auf die Box um. /go/ liegt lokal, prueft die
  // Erreichbarkeit und leitet erst dann weiter (gallery_server.go_link).
  goUrl:       (slug: "termin" | "instagram") => `/go/${slug}`,

  // pin entfaellt fuer eingeloggte Nutzer — die Session reicht dem Server.
  delete: async (p: Pick<Photo, "event" | "filename">, pin?: string): Promise<DeleteResult> => {
    const fd = new FormData();
    if (pin) fd.set("pin", pin);
    const res = await xfetch(`/api/delete/${evPath(p)}`, {
      method: "POST",
      body: fd,
    });
    return json<DeleteResult>(res);
  },

  admin: {
    me:     () => xfetch("/api/admin/me").then(json<{ authenticated: boolean; role: AdminRole | null }>),
    login:  (pin: string) => postJson("/api/admin/login", { pin }).then(json<{ ok: boolean; error?: string; role?: AdminRole }>),
    logout: () => xfetch("/api/admin/logout", { method: "POST" }).then(json<{ ok: boolean }>),
    status: () => xfetch("/api/admin/status").then(json<AdminStatus>),
    config: {
      get: () => xfetch("/api/admin/config").then(json<AdminConfig>),
      save: (data: Partial<AdminConfig>) =>
        postJson("/api/admin/config", data)
          .then(json<{ ok: boolean; wifi_restarting?: boolean }>),
    },
    printers: () =>
      xfetch("/api/admin/printers").then(json<PrinterInfo>),
    uploadLogo: async (file: File) => {
      const fd = new FormData();
      fd.set("logo", file);
      const res = await xfetch("/api/admin/logo", { method: "POST", body: fd }, UPLOAD_TIMEOUT_MS);
      return json<{ ok: boolean; error?: string }>(res);
    },
    reset: (confirm: string) =>
      postJson("/api/admin/reset", { confirm }).then(json<DeleteResult>),
    // confirm nur noetig, wenn `photos` angehakt ist — der Server prueft das.
    handover: (steps: HandoverSteps, confirm?: string) =>
      postJson("/api/admin/handover", { ...steps, confirm })
        .then(json<HandoverResult>),
    deleteEvent: (folder: string) =>
      xfetch(`/api/admin/event/${encodeURIComponent(folder)}/delete`, { method: "POST" })
        .then(json<DeleteResult>),
    // Trennt das laufende Event, ohne etwas zu loeschen — fuer Vermietungen
    // ueber mehrere Tage und zwei Feiern am selben Tag.
    newEvent: () =>
      xfetch("/api/admin/event/new", { method: "POST" })
        .then(json<{ ok: boolean; error?: string; folder: string; previous: string }>),
  },
};
