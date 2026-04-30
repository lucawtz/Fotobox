export interface Photo {
  event: string;
  filename: string;
  mtime: number;
  size: number;
}

export interface PhotosResponse {
  event_name: string;
  active_event: string;
  filter: string | null;
  count: number;
  photos: Photo[];
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

export interface EventsResponse {
  active: string;
  event_name: string;
  events: EventInfo[];
}

export const photoKey = (p: Pick<Photo, "event" | "filename">) =>
  `${p.event}/${p.filename}`;

export interface DeleteResult {
  ok: boolean;
  error?: string;
  removed?: number;
}

export interface AdminConfig {
  event_name: string;
  wifi_ssid: string;
  wifi_password: string;
  countdown_duration: number;
  admin_pin: string;
  has_logo: boolean;
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

const json = async <T,>(res: Response): Promise<T> => {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j?.error) msg = j.error; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
};

const postJson = (url: string, body: unknown) => fetch(url, {
  ...FETCH_OPTS,
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const evPath = (p: Pick<Photo, "event" | "filename">) =>
  `${encodeURIComponent(p.event)}/${encodeURIComponent(p.filename)}`;

export const api = {
  list: (event?: string | null) =>
    fetch("/api/photos" + (event ? `?event=${encodeURIComponent(event)}` : ""), FETCH_OPTS)
      .then(json<PhotosResponse>),
  count: (event?: string | null) =>
    fetch("/api/count" + (event ? `?event=${encodeURIComponent(event)}` : ""), FETCH_OPTS)
      .then(json<{ count: number }>),
  events: () => fetch("/api/events", FETCH_OPTS).then(json<EventsResponse>),

  thumbUrl:    (p: Pick<Photo, "event" | "filename">) => `/thumb/${evPath(p)}`,
  // Preview = 1280px JPEG mit Quality 80 — viel schneller über Hotspot als
  // Original. Nur Download und Originalansicht nutzen imgUrl.
  previewUrl:  (p: Pick<Photo, "event" | "filename">) => `/preview/${evPath(p)}`,
  imgUrl:      (p: Pick<Photo, "event" | "filename">) => `/img/${evPath(p)}`,
  downloadUrl: (p: Pick<Photo, "event" | "filename">) => `/download/${evPath(p)}`,
  zipUrl:      (event?: string | null) =>
    "/api/download-zip" + (event ? `?event=${encodeURIComponent(event)}` : ""),
  logoUrl:     () => `/api/admin/logo/preview?t=${Date.now()}`,

  delete: async (p: Pick<Photo, "event" | "filename">, pin: string): Promise<DeleteResult> => {
    const fd = new FormData();
    fd.set("pin", pin);
    const res = await fetch(`/api/delete/${evPath(p)}`, {
      ...FETCH_OPTS,
      method: "POST",
      body: fd,
    });
    return json<DeleteResult>(res);
  },

  admin: {
    me:     () => fetch("/api/admin/me", FETCH_OPTS).then(json<{ authenticated: boolean }>),
    login:  (pin: string) => postJson("/api/admin/login", { pin }).then(json<{ ok: boolean; error?: string }>),
    logout: () => fetch("/api/admin/logout", { ...FETCH_OPTS, method: "POST" }).then(json<{ ok: boolean }>),
    status: () => fetch("/api/admin/status", FETCH_OPTS).then(json<AdminStatus>),
    config: {
      get: () => fetch("/api/admin/config", FETCH_OPTS).then(json<AdminConfig>),
      save: (data: Partial<AdminConfig>) =>
        postJson("/api/admin/config", data).then(json<{ ok: boolean }>),
    },
    uploadLogo: async (file: File) => {
      const fd = new FormData();
      fd.set("logo", file);
      const res = await fetch("/api/admin/logo", { ...FETCH_OPTS, method: "POST", body: fd });
      return json<{ ok: boolean; error?: string }>(res);
    },
    reset: (confirm: string) =>
      postJson("/api/admin/reset", { confirm }).then(json<DeleteResult>),
  },
};
