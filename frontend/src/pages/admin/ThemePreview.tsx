import { useEffect, useMemo, useRef, useState } from "react";
import { Box } from "@mui/material";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";

/* Maßstabsgetreue Vorschau des Box-Homescreens.
 *
 * Alle Koordinaten hier stehen im 1920x1080-Raum der Box und sind 1:1 aus
 * ui.py übernommen (Layout-Konstanten + render_homescreen). Die ganze Bühne
 * wird per transform: scale() auf die Container-Breite geschrumpft — so
 * bleiben die Zahlen unten direkt mit ui.py vergleichbar, statt in Prozent
 * umgerechnet zu sein. Ändert sich dort das Layout, müssen die Konstanten
 * hier nachgezogen werden.
 *
 * Bewusst ohne echte Inhalte: die Polaroids zeigen dieselben Pastell-
 * Platzhalter wie die Box bei leerer Galerie, Live-Bild und QR-Codes sind
 * Attrappen. Es geht um Farbwirkung und Anordnung, nicht um einen
 * Live-Spiegel der Box.
 */

const W = 1920;
const H = 1080;

// ── ui.py: Layout-Konstanten ──────────────────────────────────────────────
const SIDEBAR_W     = 320;
const SIDEBAR_PAD   = 20;
const LOGO_CIRCLE_R = 80;
const ACTION_X      = 1530;
const ACTION_W      = 320;
const ACTION_H      = 110;
const ACTION_GAP    = 24;
const ACTION_RADIUS = 28;
const LIVE_OUTER_W  = 12;
const LIVE_INNER_W  = 3;
const SOCIAL_QR      = 130;  // ui.py: SOCIAL_QR_SIZE
const SOCIAL_ROW_GAP = 18;
const SOCIAL_ICON    = 22;
const SOCIAL_QR_MIN  = 104;  // ui.py: Untergrenze, unter der Codes unscannbar werden
// ui.py: UI.QR_SIZE = SOCIAL_QR_SIZE — der Galerie-Code ist bewusst genauso
// gross wie die Codes darunter (deshalb keine eigene Konstante mehr, die Card
// haengt an socialQr), und seit UI._qr_pad haben alle drei Kacheln
// denselben Cremerand. Der echte Rand haengt am Modulraster des
// Galerie-Codes (max(SOCIAL_QR_PAD, 4 * px/Modul)); die Vorschau kennt die
// URL nicht und nimmt deshalb den typischen Wert eines 25-Modul-Codes.
const SOCIAL_QR_PAD  = 20;

const POLAROID_PAD_TOP = 18;
const POLAROID_PAD_LR  = 18;
const POLAROID_PAD_BOT = 60;
const POLAROID_PIN_R   = 9;

// config.py: polaroid_frames / polaroid_photo_size / live_view_rect
const FRAMES: [number, number, number][] = [
  [567, 255, -5], [1098, 256, 5], [1633, 257, 12],
];
const PHOTO_W = 310;
const PHOTO_H = 295;
const LIVE = { x: 510, y: 540, w: 800, h: 450 };

// ui.py: _PLACEHOLDER_COLORS
const PLACEHOLDER = ["#C9A88A", "#9DBED2", "#D4A5B5"];

// config.py: "actions". Bewusst kein Theme-Wert — die Action-Farben pflegt
// der Box-Besitzer in config.py, der Mieter kann sie nicht ändern. Nur die
// Flächen/Textfarben der Outline-Buttons kommen aus dem Theme.
const ACTIONS = [
  { label: "Foto",    color: "#D4A86A", filled: true  },
  { label: "Collage", color: "#A66BB5", filled: false },
];

// Zeilenhöhen der Box-Schrift, gemessen mit ui._font() in DejaVu Sans. Die
// früheren Zahlen stammten aus der Zeit des pygame-Fallbacks (freesansbold)
// und lagen rund ein Drittel zu niedrig — damit sass die ganze
// Sidebar-Rechnung daneben.
const F_EVENT_PT = 38, F_EVENT_H  = 43;   // ui.py: _f_event
const F_SUB_PT   = 24, F_SUB_H    = 27;   // ui.py: _f_sub
const F_NORMAL_PT = 38, F_NORMAL_H = 43;  // ui.py: _f_normal
const F_LABEL_PT  = 19, F_LABEL_H  = 22;  // ui.py: _f_label
const F_SMALL_H   = 27;                   // ui.py: _f_small

// ui.py: _status_bar_height() = _f_small.get_height() + 10
const STATUS_H = F_SMALL_H + 10;

// Untergrenzen aus ui.py, unter die der Header nicht schrumpft.
const EVENT_MIN_PT = 22;
const SUB_MIN_PT   = 16;

// ui.py: SIDEBAR_W - 30
const HEADER_W = SIDEBAR_W - 30;
const HEADER_LINE_GAP  = 2;
const HEADER_BLOCK_GAP = 8;

// ui.py waehlt per match_font die erste echte Schrift — auf dem Pi ist das
// DejaVu Sans. Im Browser dieselbe zuerst, damit die Umbrueche der Vorschau
// denen der Box moeglichst nahe kommen.
const FONT = '"DejaVu Sans", "Noto Sans", "Liberation Sans", Arial, sans-serif';

export interface PreviewProps {
  theme: Record<string, string>;
  eventName: string;
  subtitle: string;
  /** URL des aktiven Logos oder null → dann Initialen wie auf der Box. */
  logoUrl: string | null;
  wifiSsid: string;
  wifiPassword: string;
  instagramUrl: string;
  bookingUrl: string;
  /** Beschriftung der Buchungs-Reihe (Owner-Setting booking_label). */
  bookingLabel: string;
  /** Ob ein fertiger Code hinterlegt ist. Ohne zeichnet die Box Glyph+Text. */
  hasInstagramQr: boolean;
  hasBookingQr: boolean;
  /** Ob die Box selbst der Access-Point ist (Owner-Setting hotspot_enabled).
   *  Nur dann traegt die WLAN-Box den Hinweis auf ein offenes Netz. */
  hotspotEnabled: boolean;
}

/** ui.py: _event_initials */
const initialsOf = (name: string): string => {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "FB";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
};

/** ui.py: _instagram_handle */
const instaHandle = (url: string): string => {
  const s = url.trim().replace(/\/+$/, "");
  if (s.includes("instagram.com/")) {
    const h = s.split("instagram.com/").pop()!.split("/")[0].split("?")[0];
    if (h) return `@${h}`;
  }
  if (s.startsWith("@")) return s;
  return "Instagram";
};

/** Dekoratives QR-Muster. Der echte Code entsteht erst auf der Box
 *  (ui.py:_make_qr) — hier geht es nur darum, dass die Sidebar-Proportionen
 *  stimmen. Deterministisch, damit die Vorschau nicht bei jedem Render flimmert. */
function QrArt({ size, modules }: { size: number; modules: number }) {
  const rects = useMemo(() => {
    const out: { x: number; y: number }[] = [];
    let seed = 0x2f6e2b1 + modules;
    const rnd = () => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };
    const inFinder = (x: number, y: number) =>
      (x < 8 && y < 8) ||
      (x >= modules - 8 && y < 8) ||
      (x < 8 && y >= modules - 8);
    for (let y = 0; y < modules; y++) {
      for (let x = 0; x < modules; x++) {
        if (inFinder(x, y)) continue;
        if (rnd() > 0.55) out.push({ x, y });
      }
    }
    return out;
  }, [modules]);

  const finder = (fx: number, fy: number) => (
    <g key={`f${fx}-${fy}`}>
      <rect x={fx} y={fy} width={7} height={7} fill="none" stroke="#000" strokeWidth={1} />
      <rect x={fx + 2} y={fy + 2} width={3} height={3} fill="#000" />
    </g>
  );

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${modules} ${modules}`}
      shapeRendering="crispEdges"
      aria-hidden
      style={{ display: "block", background: "#FFF" }}
    >
      {rects.map((r) => (
        <rect key={`${r.x}-${r.y}`} x={r.x} y={r.y} width={1} height={1} fill="#000" />
      ))}
      {finder(0, 0)}
      {finder(modules - 7, 0)}
      {finder(0, modules - 7)}
    </svg>
  );
}

/** ui.py: _domain_of — "https://bytebots.de/termine" -> "bytebots.de". */
const domainOf = (url: string): string => {
  const rest = url.split("://").pop()!.split("/")[0];
  return rest.startsWith("www.") ? rest.slice(4) : rest;
};

// ── Textmessung ───────────────────────────────────────────────────────────
// Ein einzelnes Canvas fuer alle Messungen. Ohne echte Breiten laesst sich
// _fit_text nicht nachbilden, und genau daran haben sich die frueheren
// Ein-Zeile-pro-Block-Annahmen aufgehaengt.
let _ctx: CanvasRenderingContext2D | null = null;
const measure = (text: string, pt: number, bold: boolean): number => {
  if (!_ctx) _ctx = document.createElement("canvas").getContext("2d");
  if (!_ctx) return text.length * pt * 0.55;      // Canvas gesperrt: schaetzen
  _ctx.font = `${bold ? "700 " : ""}${pt}px ${FONT}`;
  return _ctx.measureText(text).width;
};

/** ui.py: UI._wrap */
const wrap = (text: string, pt: number, bold: boolean,
              maxW: number, maxLines: number): string[] | null => {
  const lines: string[] = [];
  let cur = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    if (measure(word, pt, bold) > maxW) return null;
    const probe = cur ? `${cur} ${word}` : word;
    if (measure(probe, pt, bold) <= maxW) { cur = probe; continue; }
    lines.push(cur);
    cur = word;
    if (lines.length === maxLines) return null;
  }
  if (cur) lines.push(cur);
  return lines.length > 0 && lines.length <= maxLines ? lines : null;
};

/** ui.py: UI._hard_wrap — bricht notfalls im Wort und kuerzt mit "…". */
const hardWrap = (text: string, pt: number, bold: boolean,
                  maxW: number, maxLines: number): string[] => {
  const lines: string[] = [];
  let cur = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    for (const ch of (cur ? ` ${word}` : word)) {
      if (measure(cur + ch, pt, bold) <= maxW) { cur += ch; continue; }
      lines.push(cur);
      if (lines.length === maxLines) {
        let last = lines[lines.length - 1];
        while (last && measure(`${last}…`, pt, bold) > maxW) last = last.slice(0, -1);
        lines[lines.length - 1] = `${last}…`;
        return lines;
      }
      cur = ch.trimStart();
    }
  }
  if (cur) lines.push(cur);
  return lines.length ? lines : [""];
};

interface HeaderBlock { pt: number; lineH: number; bold: boolean; lines: string[]; dim: boolean }

/** ui.py: UI._fit_text + UI._header_blocks. */
const headerBlocks = (name: string, sub: string): HeaderBlock[] => {
  const out: HeaderBlock[] = [];
  const specs: [string, number, number, number, boolean, boolean][] = [
    // Text, Start-pt, Referenz-Zeilenhoehe, Untergrenze, fett, gedimmt
    [name.trim(), F_EVENT_PT, F_EVENT_H, EVENT_MIN_PT, true,  false],
    [sub.trim(),  F_SUB_PT,   F_SUB_H,   SUB_MIN_PT,   false, true ],
  ];
  const maxLines = [2, 3];
  specs.forEach(([text, startPt, refH, minPt, bold, dim], i) => {
    if (!text) return;
    let pt = startPt;
    let lines: string[] | null = null;
    while (pt > minPt) {
      lines = wrap(text, pt, bold, HEADER_W, maxLines[i]);
      if (lines) break;
      pt -= 1;
    }
    if (!lines) { pt = minPt; lines = hardWrap(text, pt, bold, HEADER_W, maxLines[i]); }
    // Zeilenhoehe skaliert mit der Punktgroesse — refH gilt fuer startPt.
    out.push({ pt, lineH: Math.round((refH / startPt) * pt), bold, lines, dim });
  });
  return out;
};

// ── WLAN-Box ──────────────────────────────────────────────────────────────
/** Eine Zeile der WLAN-Box, ui.py: _wifi_rows liefert (Label, Wert, Font).
 *  `label: null` ist kein Sonderfall, sondern die Notiz zur Zeile darueber —
 *  ohne Beschriftung und in kleinerer Schrift. */
interface WifiRow {
  label: string | null;
  value: string;
  sizePt: number;
  lineH: number;
  weight: number;
}

// ── Social-Reihen ─────────────────────────────────────────────────────────
interface SocialRow {
  kind: "instagram" | "calendar";
  line1: string;
  line2: string | null;
  qr: boolean;
}

/** ui.py: UI._social_row_height. */
const rowHeight = (row: SocialRow, qrSize: number): number => {
  let textH = F_SUB_H;
  if (row.line2) textH += F_LABEL_H + 2;
  return row.qr
    ? qrSize + SOCIAL_QR_PAD * 2 + 6 + textH + SOCIAL_ROW_GAP
    : Math.max(textH, SOCIAL_ICON) + SOCIAL_ROW_GAP;
};

// ui.py:_group_height — die Card zaehlt mit der Kantenlaenge, die gerade
// getestet wird, nicht mit einer festen. Sonst rechnet die Pruefung mit einer
// Karte, die es hinterher nicht gibt.
const groupHeight = (rows: SocialRow[], qrSize: number, captionH: number): number =>
  (qrSize + SOCIAL_QR_PAD * 2) + captionH +
  (rows.length ? 16 + rows.reduce((h, r) => h + rowHeight(r, qrSize), 0) : 0);

/** ui.py: UI._social_layout — erst schrumpfen, dann Codes abgeben. */
const socialLayout = (input: SocialRow[], room: number, captionH: number) => {
  const rows = input.map((r) => ({ ...r }));
  for (;;) {
    let size = SOCIAL_QR;
    while (size > SOCIAL_QR_MIN && groupHeight(rows, size, captionH) > room) {
      size -= 2;
    }
    if (groupHeight(rows, size, captionH) <= room) return { rows, size };
    const idx = rows.map((r, i) => (r.qr ? i : -1)).filter((i) => i >= 0).pop();
    if (idx === undefined) return { rows, size };
    rows[idx].qr = false;
  }
};

/** ui.py: _draw_instagram_icon / _draw_calendar_icon — beide in accent. */
function SocialIcon({ kind, color }: { kind: "instagram" | "calendar"; color: string }) {
  const s = SOCIAL_ICON;   // viewBox bleibt 18, das SVG skaliert mit
  if (kind === "instagram") {
    return (
      <svg width={s} height={s} viewBox="0 0 18 18" aria-hidden style={{ display: "block" }}>
        <rect x={1} y={1} width={16} height={16} rx={3.5} fill="none" stroke={color} strokeWidth={2} />
        <circle cx={9} cy={9} r={4} fill="none" stroke={color} strokeWidth={2} />
        <circle cx={13} cy={5} r={1} fill={color} />
      </svg>
    );
  }
  return (
    <svg width={s} height={s} viewBox="0 0 18 18" aria-hidden style={{ display: "block" }}>
      <rect x={1} y={5} width={16} height={12} rx={2} fill="none" stroke={color} strokeWidth={2} />
      <rect x={5} y={0} width={3} height={6} fill={color} />
      <rect x={10} y={0} width={3} height={6} fill={color} />
      <line x1={1} y1={11} x2={17} y2={11} stroke={color} strokeWidth={1} />
    </svg>
  );
}

export default function ThemePreview(props: PreviewProps) {
  const { theme, eventName, subtitle, logoUrl,
          wifiSsid, wifiPassword, hotspotEnabled, instagramUrl, bookingUrl,
          bookingLabel, hasInstagramQr, hasBookingQr } = props;

  const wrapRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);

  // Bühne auf die Container-Breite skalieren.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      if (w > 0) setScale(w / W);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const c = (key: string, fallback = "#000000") => theme[key] ?? fallback;

  // ── Header umbrechen wie ui.py:_fit_text ────────────────────────────────
  const header = useMemo(
    () => headerBlocks(eventName, subtitle),
    [eventName, subtitle],
  );
  const headerBottom =
    SIDEBAR_PAD + LOGO_CIRCLE_R * 2 + 24 +
    header.reduce(
      (h, b) => h + b.lines.length * b.lineH
              + (b.lines.length - 1) * HEADER_LINE_GAP + HEADER_BLOCK_GAP,
      0,
    );

  // ── WLAN-Box (ui.py:_wifi_rows / _wifi_box_metrics) ─────────────────────
  // Zwei Zeilen, nicht drei: die Galerie-Adresse stand hier einmal und kostete
  // die QR-Gruppe darueber die 69 px, die der Instagram-Code braucht. Jede
  // Zeile, die hier dazukommt, nimmt sie ihm wieder weg.
  const wifiRowDefs: WifiRow[] = [];
  if (wifiSsid.trim()) {
    wifiRowDefs.push({ label: "WLAN", value: wifiSsid.trim(),
                       sizePt: F_NORMAL_PT, lineH: F_NORMAL_H, weight: 700 });
  }
  if (wifiPassword.trim()) {
    wifiRowDefs.push({ label: "Passwort", value: wifiPassword.trim(),
                       sizePt: F_NORMAL_PT, lineH: F_NORMAL_H, weight: 700 });
  } else if (hotspotEnabled) {
    // Ohne diesen Hinweis sucht der Gast nach einem Passwort, das es nicht
    // gibt. Er darf aber auch nicht aussehen wie eines — deshalb ohne Label
    // und in der kleinen Schrift, als Notiz zur Zeile darueber. Genau so
    // steht es in ui.py:_wifi_rows, und genau diese Zeile fehlte der
    // Vorschau: bei offenem WLAN zeigte sie gar nichts.
    wifiRowDefs.push({ label: null, value: "Kein Passwort nötig",
                       sizePt: F_SUB_PT, lineH: F_SUB_H, weight: 400 });
  }
  const wifiRows = wifiRowDefs.length;
  // Zeilen ohne Label tragen auch dessen Hoehe nicht — sonst saesse die Box
  // hoeher als auf der Box, und die QR-Gruppe darueber bekaeme in der
  // Vorschau Platz, den sie in Wirklichkeit nicht hat (ui.py:
  // _wifi_box_metrics, _qr_group_bounds).
  const wifiBoxH = wifiRows
    ? 22 + wifiRowDefs.reduce(
        (h, r) => h + (r.label ? F_LABEL_H + 4 : 0) + r.lineH + 14, 0)
    : 0;
  // ui.py rechnet den Rand aus der Status-Bar statt ihn zu verdrahten.
  const wifiTop  = wifiRows ? H - (STATUS_H + 12) - wifiBoxH : H;

  // ── Social-Reihen (ui.py:_social_rows / _social_layout) ─────────────────
  // Eine Reihe traegt nur dann einen eigenen Code, wenn er auch hinterlegt
  // ist — sonst zeichnet die Box Glyph und Text. Und Glyphen gibt es nur,
  // solange KEINE Reihe einen Code traegt.
  const allRows: SocialRow[] = [];
  if (instagramUrl.trim()) {
    allRows.push({ kind: "instagram", line1: instaHandle(instagramUrl),
                   line2: null, qr: hasInstagramQr });
  }
  if (bookingUrl.trim()) {
    allRows.push({ kind: "calendar", line1: bookingLabel.trim() || "Termin buchen",
                   line2: domainOf(bookingUrl), qr: hasBookingQr });
  }

  // ui.py:_draw_qr_card bringt den Galerie-Code auf dieselbe Kantenlaenge wie
  // die Kacheln darunter — die Card haengt damit an socialQr, nicht an QR_SIZE.
  const captionH  = F_SUB_H + 12;
  const qrTop     = headerBottom + 20;
  const qrBottom  = wifiTop - 20;          // ui.py: _qr_group_bounds

  // Zwei Stufen wie ui.py:_social_layout — erst Kacheln schrumpfen, dann der
  // untersten Reihe den Code nehmen.
  const { rows: socialRows, size: socialQr } = useMemo(
    () => socialLayout(allRows, qrBottom - qrTop, captionH),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(allRows), qrBottom - qrTop, captionH],
  );
  const cardSize = socialQr + SOCIAL_QR_PAD * 2;
  const glyphs = !socialRows.some((r) => r.qr);

  const socialH = socialRows.length
    ? 16 + socialRows.reduce((h, r) => h + rowHeight(r, socialQr), 0)
    : 0;
  const groupH  = cardSize + captionH + socialH;
  const qrY     = Math.max(qrTop, qrTop + Math.floor((qrBottom - qrTop - groupH) / 2));

  const captionY = qrY + cardSize + 12;
  const socialY  = captionY + F_SUB_H + 16;

  // ── Action-Buttons (ui.py:_action_rects) ────────────────────────────────
  const totalActionH = ACTIONS.length * ACTION_H + (ACTIONS.length - 1) * ACTION_GAP;
  const actionY0 = Math.max(80, LIVE.y + LIVE.h / 2 - totalActionH / 2);

  return (
    <Box
      ref={wrapRef}
      sx={{
        position: "relative",
        width: "100%",
        aspectRatio: "16 / 9",
        overflow: "hidden",
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "grey.900",
      }}
    >
      <Box
        aria-label="Vorschau des Box-Bildschirms"
        sx={{
          position: "absolute",
          top: 0,
          left: 0,
          width: W,
          height: H,
          transformOrigin: "top left",
          transform: `scale(${scale})`,
          // Bis der ResizeObserver gefeuert hat wäre die Bühne in Originalgröße
          // kurz sichtbar — das gibt einen sichtbaren Sprung beim Mounten.
          visibility: scale > 0 ? "visible" : "hidden",
          background: `linear-gradient(180deg, ${c("bg_top")} 0%, ${c("bg_bottom")} 100%)`,
          fontFamily: FONT,
          userSelect: "none",
        }}
      >
        {/* ── Polaroid-Wand ─────────────────────────────────────────────── */}
        {FRAMES.map(([cx, cy, angle], i) => {
          const fw = PHOTO_W + POLAROID_PAD_LR * 2;
          const fh = PHOTO_H + POLAROID_PAD_TOP + POLAROID_PAD_BOT;
          return (
            <Box
              key={i}
              sx={{
                position: "absolute",
                left: cx - fw / 2,
                top: cy - fh / 2,
                width: fw,
                height: fh,
                // pygame.rotozoom dreht gegen den Uhrzeigersinn, CSS mit ihm.
                transform: `rotate(${-angle}deg)`,
                bgcolor: c("polaroid_frame"),
                borderRadius: "2px",
                boxShadow: "6px 10px 0 rgba(0,0,0,.35)",
              }}
            >
              <Box
                sx={{
                  position: "absolute",
                  left: POLAROID_PAD_LR,
                  top: POLAROID_PAD_TOP,
                  width: PHOTO_W,
                  height: PHOTO_H,
                  // ui.py:_PLACEHOLDER_COLORS — der Look der leeren Box.
                  bgcolor: PLACEHOLDER[i % PLACEHOLDER.length],
                }}
              />
              <Box
                sx={{
                  position: "absolute",
                  left: fw / 2 - POLAROID_PIN_R,
                  top: 6,
                  width: POLAROID_PIN_R * 2,
                  height: POLAROID_PIN_R * 2,
                  borderRadius: "50%",
                  bgcolor: c("polaroid_pin"),
                  boxShadow: "1px 2px 0 rgba(0,0,0,.4)",
                }}
              />
            </Box>
          );
        })}

        {/* ── Live-View mit Rahmen ──────────────────────────────────────── */}
        <Box
          sx={{
            position: "absolute",
            left: LIVE.x - LIVE_OUTER_W,
            top: LIVE.y - LIVE_OUTER_W,
            width: LIVE.w + LIVE_OUTER_W * 2,
            height: LIVE.h + LIVE_OUTER_W * 2,
            bgcolor: c("live_outer"),
            borderRadius: "14px",
          }}
        />
        <Box
          sx={{
            position: "absolute",
            left: LIVE.x,
            top: LIVE.y,
            width: LIVE.w,
            height: LIVE.h,
            boxSizing: "border-box",
            bgcolor: c("live_bg"),
            border: `${LIVE_INNER_W}px solid ${c("live_inner")}`,
            borderRadius: "6px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "18px",
            color: "rgba(255,255,255,.45)",
          }}
        >
          <PhotoCameraRoundedIcon sx={{ fontSize: 110 }} />
          <Box sx={{ fontSize: 34 }}>Live-Vorschau der Kamera</Box>
        </Box>

        {/* ── Action-Buttons ────────────────────────────────────────────── */}
        {ACTIONS.map((a, i) => {
          const top = actionY0 + i * (ACTION_H + ACTION_GAP);
          const labelColor = a.filled ? c("text", "#FFFFFF") : a.color;
          return (
            <Box
              key={a.label}
              sx={{
                position: "absolute",
                left: ACTION_X,
                top,
                width: ACTION_W,
                height: ACTION_H,
                boxSizing: "border-box",
                borderRadius: `${ACTION_RADIUS}px`,
                bgcolor: a.filled ? a.color : c("panel_bg"),
                border: a.filled ? "none" : `2px solid ${a.color}`,
                boxShadow: "0 4px 0 rgba(0,0,0,.14), 0 8px 12px rgba(0,0,0,.10)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: labelColor,
                fontSize: 60,
                fontWeight: 700,
              }}
            >
              {a.label}
              <svg
                width={20}
                height={30}
                viewBox="0 0 20 30"
                aria-hidden
                style={{ position: "absolute", right: 19, top: ACTION_H / 2 - 15 }}
              >
                <polyline
                  points="2,3 14,15 2,27"
                  fill="none"
                  stroke={labelColor}
                  strokeWidth={3}
                />
              </svg>
            </Box>
          );
        })}

        {/* ── Sidebar ───────────────────────────────────────────────────── */}
        <Box
          sx={{
            position: "absolute",
            left: 0,
            top: 0,
            width: SIDEBAR_W,
            height: H,
            bgcolor: c("sidebar_bg"),
          }}
        >
          {/* Logo-Kreis */}
          <Box
            sx={{
              position: "absolute",
              left: SIDEBAR_W / 2 - LOGO_CIRCLE_R,
              top: SIDEBAR_PAD,
              width: LOGO_CIRCLE_R * 2,
              height: LOGO_CIRCLE_R * 2,
              borderRadius: "50%",
              bgcolor: c("logo_circle"),
              display: "grid",
              placeItems: "center",
              overflow: "hidden",
            }}
          >
            {logoUrl ? (
              <Box
                component="img"
                src={logoUrl}
                alt=""
                sx={{
                  // ui.py:_make_circular_logo — cover auf 2*(R-6), rund geschnitten.
                  width: (LOGO_CIRCLE_R - 6) * 2,
                  height: (LOGO_CIRCLE_R - 6) * 2,
                  borderRadius: "50%",
                  objectFit: "cover",
                  display: "block",
                }}
              />
            ) : (
              <Box sx={{ fontSize: 72, fontWeight: 700, color: c("logo_text") }}>
                {initialsOf(eventName)}
              </Box>
            )}
          </Box>

          {/* Event-Name + Subtitle */}
          <Box
            sx={{
              position: "absolute",
              left: 15,
              top: SIDEBAR_PAD + LOGO_CIRCLE_R * 2 + 24,
              width: SIDEBAR_W - 30,
              textAlign: "center",
            }}
          >
            {header.map((b, bi) => (
              <Box key={bi} sx={{ mt: bi ? `${HEADER_BLOCK_GAP}px` : 0 }}>
                {b.lines.map((line, li) => (
                  <Box
                    key={li}
                    sx={{
                      fontSize: b.pt,
                      fontWeight: b.bold ? 700 : 400,
                      lineHeight: `${b.lineH + HEADER_LINE_GAP}px`,
                      color: b.dim ? c("sidebar_dim") : c("sidebar_text"),
                      whiteSpace: "nowrap",
                    }}
                  >
                    {line}
                  </Box>
                ))}
              </Box>
            ))}
          </Box>

          {/* Galerie-QR-Card */}
          <Box
            sx={{
              position: "absolute",
              left: SIDEBAR_W / 2 - cardSize / 2,
              top: qrY,
              width: cardSize,
              height: cardSize,
              borderRadius: "10px",
              bgcolor: c("logo_circle"),
              display: "grid",
              placeItems: "center",
            }}
          >
            {/* 25 Module: der Code traegt den Galerie-Link. Der WLAN-Zugang
                stand hier einmal und waere bei 29 gelandet — warum er
                wieder weg ist, steht in config.py. */}
            <QrArt size={socialQr} modules={25} />
          </Box>
          <Box
            sx={{
              position: "absolute",
              left: 0,
              top: captionY,
              width: SIDEBAR_W,
              textAlign: "center",
              fontSize: F_SUB_PT,
              lineHeight: `${F_SUB_H}px`,
              color: c("sidebar_text"),
            }}
          >
            {/* ui.py:_qr_caption */}
            Fotos auf&apos;s Handy
          </Box>

          {/* Instagram / Terminbuchung — gestapelt wie ui.py:_draw_social_links.
              Frueher standen Code, Glyph und Text hier nebeneinander; die Box
              setzt sie bewusst untereinander, weil in 320 px Breite sonst fuer
              den Text nichts uebrig bleibt. Und Code UND Glyph gab es nie: das
              eine ersetzt das andere. */}
          {socialRows.length > 0 && (
            <Box
              sx={{
                position: "absolute",
                left: 0,
                top: socialY,
                width: SIDEBAR_W,
              }}
            >
              {socialRows.map((row, i) => {
                const top = socialRows
                  .slice(0, i)
                  .reduce((h, r) => h + rowHeight(r, socialQr), 0);
                return (
                  <Box
                    key={row.kind}
                    sx={{ position: "absolute", top, left: 0, width: SIDEBAR_W }}
                  >
                    {row.qr ? (
                      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <Box
                          sx={{
                            width: socialQr + SOCIAL_QR_PAD * 2,
                            height: socialQr + SOCIAL_QR_PAD * 2,
                            borderRadius: "8px",
                            bgcolor: c("logo_circle"),
                            display: "grid",
                            placeItems: "center",
                          }}
                        >
                          <QrArt size={socialQr} modules={row.kind === "instagram" ? 41 : 33} />
                        </Box>
                        <Box sx={{ height: "6px" }} />
                        <Box sx={{ fontSize: F_SUB_PT, lineHeight: `${F_SUB_H}px`,
                                   color: c("sidebar_text"), whiteSpace: "nowrap" }}>
                          {row.line1}
                        </Box>
                        {row.line2 && (
                          <Box sx={{ fontSize: F_LABEL_PT, fontWeight: 700,
                                     lineHeight: `${F_LABEL_H + 2}px`,
                                     color: c("accent"), whiteSpace: "nowrap" }}>
                            {row.line2}
                          </Box>
                        )}
                      </Box>
                    ) : (
                      <Box sx={{ display: "flex", justifyContent: "center",
                                 alignItems: "center", gap: glyphs ? "10px" : 0 }}>
                        {glyphs && <SocialIcon kind={row.kind} color={c("accent")} />}
                        <Box>
                          <Box sx={{ fontSize: F_SUB_PT, lineHeight: `${F_SUB_H}px`,
                                     color: c("sidebar_text"), whiteSpace: "nowrap" }}>
                            {row.line1}
                          </Box>
                          {row.line2 && (
                            <Box sx={{ fontSize: F_LABEL_PT, fontWeight: 700,
                                       lineHeight: `${F_LABEL_H + 2}px`,
                                       color: c("accent"), whiteSpace: "nowrap" }}>
                              {row.line2}
                            </Box>
                          )}
                        </Box>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>
          )}

          {/* WLAN-Box */}
          {wifiRows > 0 && (
            <Box
              sx={{
                position: "absolute",
                left: 20,
                top: wifiTop,
                width: SIDEBAR_W - 40,
                height: wifiBoxH,
                boxSizing: "border-box",
                borderRadius: "10px",
                bgcolor: c("panel_bg"),
                border: `2px solid ${c("panel_border")}`,
                pt: "14px",
                px: "16px",
              }}
            >
              {wifiRowDefs.map((row, i) => (
                  <Box key={row.label ?? `unlabelled-${i}`} sx={{ mb: "12px" }}>
                    {row.label && (
                      <Box
                        sx={{
                          fontSize: F_LABEL_PT,
                          fontWeight: 700,
                          lineHeight: `${F_LABEL_H}px`,
                          color: c("sidebar_dim"),
                          mb: "2px",
                        }}
                      >
                        {row.label}
                      </Box>
                    )}
                    <Box
                      sx={{
                        fontSize: row.sizePt,
                        fontWeight: row.weight,
                        lineHeight: `${row.lineH}px`,
                        color: c("sidebar_text"),
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {row.value}
                    </Box>
                  </Box>
                ))}
            </Box>
          )}
        </Box>

        {/* ── Status-Bar ────────────────────────────────────────────────── */}
        <Box
          sx={{
            position: "absolute",
            left: 0,
            top: H - STATUS_H,
            width: W,
            height: STATUS_H,
            bgcolor: "rgba(0,0,0,.63)",
            display: "flex",
            alignItems: "center",
            gap: "60px",
            pl: "20px",
            fontSize: 26,
          }}
        >
          <Box sx={{ color: "rgb(80,200,80)" }}>Kamera: OK</Box>
          <Box sx={{ color: "rgb(155,120,65)" }}>Speicher: 24.6 GB</Box>
          <Box sx={{ color: "rgb(155,120,65)" }}>Fotos: 128</Box>
          <Box sx={{ color: "rgb(155,120,65)" }}>Hotspot: aktiv</Box>
        </Box>
      </Box>
    </Box>
  );
}
