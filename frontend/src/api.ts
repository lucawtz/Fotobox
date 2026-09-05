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

/** Antwort auf den Neustart-Knopf. `eta_s` ist die geschaetzte Wartezeit bis
 *  die Box wieder da ist, `retry_after` bei 429 die Restsperre in Sekunden. */
export interface RestartResult {
  ok: boolean;
  error?: string;
  eta_s?: number;
  retry_after?: number;
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
  /** Ob nach dem Entfernen des Mieter-Logos ein Standard-Logo greift. Ist es
   *  false, zeigt die Box danach die Initialen des Event-Namens. */
  has_default_logo: boolean;
  role: AdminRole;
  theme: ThemeColors;
  instagram_url: string;
  booking_url: string;
  /** Beschriftung der Buchungs-Reihe auf dem Homescreen (Owner-Setting). */
  booking_label: string;
  /** Ob fuer Instagram / Buchung ein fertiger Code hinterlegt ist. Die Box
   *  zeigt sonst nur Glyph und Text — die Vorschau muss das nachbilden. */
  has_instagram_qr: boolean;
  has_booking_qr: boolean;
  insecure_defaults?: string[];
  print_enabled: boolean;
  printer_name: string;
  print_copies: number;
  print_mode: "auto" | "cover" | "fit";
  /** Randlos-Korrektur, beide vom Server schon auf gueltige Werte begrenzt.
   *  `print_scale_pct` zieht das Bild auf beiden Achsen gleich weit zusammen,
   *  `print_bleed_mm` ist der Ueberstand je Blattrand als
   *  [lange Kante, kurze Kante] in mm — die feinere der beiden Schrauben. */
  print_scale_pct: number;
  print_bleed_mm: [number, number];
  /** Zeichengrenzen fuer event_name / subtitle, ausgemessen gegen die
   *  Sidebar-Breite der Box (config.py: EVENT_NAME_MAX_CHARS / SUBTITLE_MAX_CHARS).
   *  Kommen vom Server, damit das Panel sie nicht ein zweites Mal verdrahtet. */
  event_name_max: number;
  subtitle_max: number;
  // WLAN sehen beide Rollen — der Gastgeber soll fuer seine Veranstaltung
  // SSID/Passwort anpassen koennen. Nur die PINs bleiben admin-only, sonst
  // koennte der Host den Admin-PIN auslesen und sich selbst hochstufen.
  wifi_ssid?: string;
  wifi_password?: string;
  /** Galerie-Adresse ohne Schema, wie sie auf dem Boxschirm steht
   *  (z. B. "fotobox.internal"). Nur zum Anzeigen. */
  gallery_address?: string;
  /** Ob die Box selbst der Access-Point ist. Owner-Setting, nur lesbar —
   *  die Theme-Vorschau braucht es, weil die Box den Hinweis "Kein Passwort
   *  noetig" nur dann schreibt (ui.py: _wifi_rows). */
  hotspot_enabled?: boolean;
  admin_pin?: string;
  host_pin?: string;
}

/** Was der Drucker selbst meldet (IPP printer-state-reasons), schon uebersetzt.
 *  `blocking` heisst: ein Druckversuch bringt sicher nichts (Papier leer,
 *  Deckel offen). Alles andere ist ein Hinweis, kein Hindernis. */
export interface PrinterReason {
  key: string;
  severity: "error" | "warning" | "report";
  text: string;
  blocking: boolean;
}

export interface Printer {
  name: string;
  state: string;
  ready: boolean;
  line: string;
  reasons: PrinterReason[];
  /** true/false = haengt sicher am USB / sicher nicht. null = nicht pruefbar
   *  (Netzwerkdrucker, kein lesbares sysfs) — dann wird nichts behauptet. */
  connected: boolean | null;
  /** CUPS-Attrappe (Braille, PDF, Fax) statt Fotodrucker. */
  virtual: boolean;
}

export interface PrinterInfo {
  ok: boolean;
  error?: string;
  printers: Printer[];
  default: string | null;
  /** `state` ist der CUPS-Zustand des aufgeloesten Druckers oder null.
   *  Noetig, weil `available` bei 'unknown' bewusst true ist — die UI soll
   *  "geprueft bereit" trotzdem von "angeboten, aber nicht auslesbar"
   *  unterscheiden koennen. */
  status: {
    available: boolean;
    printer: string | null;
    message: string;
    state: "idle" | "printing" | "disabled" | "unknown" | null;
    reasons: PrinterReason[];
    connected: boolean | null;
  };
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
// Der Testdruck rendert erst die Seite und wartet dann, bis CUPS den Auftrag
// annimmt (printing.print_photo: lp-Timeout 20 s). Die regulaeren 12 s wuerden
// genau dann abbrechen, wenn der Drucker langsam antwortet — und der Admin
// haette einen Timeout-Fehler vor einem Blatt, das trotzdem kommt.
const PRINT_TEST_TIMEOUT_MS = 45_000;

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
    // Druckt eine Testseite mit den GESPEICHERTEN Einstellungen.
    printTest: () =>
      xfetch("/api/admin/print-test", { method: "POST" }, PRINT_TEST_TIMEOUT_MS)
        .then(json<{ ok: boolean; message?: string; error?: string }>),
    uploadLogo: async (file: File) => {
      const fd = new FormData();
      fd.set("logo", file);
      const res = await xfetch("/api/admin/logo", { method: "POST", body: fd }, UPLOAD_TIMEOUT_MS);
      return json<{ ok: boolean; error?: string }>(res);
    },
    // Entfernt nur das hochgeladene Logo. Das Standard-Logo des Box-Besitzers
    // bleibt liegen und greift danach wieder.
    deleteLogo: () =>
      xfetch("/api/admin/logo", { method: "DELETE" })
        .then(json<{ ok: boolean; error?: string; has_logo: boolean; has_default_logo: boolean }>),
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
    // Beendet die Box absichtlich — systemd startet sie neu. Die Antwort
    // kommt noch vor dem SIGTERM raus; danach ist der Server fuer ein paar
    // Sekunden weg, und mit ihm der Hotspot.
    restart: () =>
      postJson("/api/admin/restart", {}).then(json<RestartResult>),
  },
};
