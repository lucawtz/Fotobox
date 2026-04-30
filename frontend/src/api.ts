export interface Photo {
  filename: string;
  mtime: number;
  size: number;
}

export interface PhotosResponse {
  event_name: string;
  count: number;
  photos: Photo[];
}

export interface DeleteResult {
  ok: boolean;
  error?: string;
}

const json = async <T,>(res: Response): Promise<T> => {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j?.error) msg = j.error; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
};

export const api = {
  list: () => fetch("/api/photos").then(json<PhotosResponse>),
  count: () => fetch("/api/count").then(json<{ count: number }>),

  thumbUrl: (filename: string) => `/thumb/${encodeURIComponent(filename)}`,
  imgUrl:   (filename: string) => `/img/${encodeURIComponent(filename)}`,
  downloadUrl: (filename: string) => `/download/${encodeURIComponent(filename)}`,

  delete: async (filename: string, pin: string): Promise<DeleteResult> => {
    const fd = new FormData();
    fd.set("pin", pin);
    const res = await fetch(`/api/delete/${encodeURIComponent(filename)}`, {
      method: "POST",
      body: fd,
    });
    return json<DeleteResult>(res);
  },
};
