// Vorgefertigte Farbschemen für unterschiedliche Event-Typen.
//
// Jedes Preset setzt ALLE Theme-Felder, weil das Backend Theme-Updates
// mergiert (gallery_server.py:776). Würden wir nur die 6 UI-Pickerfelder
// schreiben, blieben Felder wie polaroid_frame oder logo_circle vom
// vorherigen Theme stehen und das Ergebnis sähe inkonsistent aus.

export interface ThemePreset {
  id: string;
  name: string;
  description: string;
  // Bis zu vier Hauptfarben fürs Vorschau-Thumbnail (in Reihenfolge sichtbar).
  swatch: [string, string, string, string];
  colors: Record<string, string>;
}

export const THEME_PRESETS: ThemePreset[] = [
  {
    id: "vintage-cream",
    name: "Vintage Cream",
    description: "Warmes Creme-Gold — klassische Hochzeit",
    swatch: ["#D5BB99", "#3D2818", "#D4A86A", "#C24838"],
    colors: {
      bg_top:         "#D5BB99",
      bg_bottom:      "#B89A75",
      sidebar_bg:     "#3D2818",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#A09080",
      logo_circle:    "#F5EBD8",
      logo_text:      "#A36B3F",
      panel_bg:       "#1F1812",
      panel_border:   "#7A5A35",
      polaroid_frame: "#FAEED9",
      polaroid_pin:   "#C24838",
      live_bg:        "#1A140F",
      live_outer:     "#5A3A1C",
      live_inner:     "#C9A06A",
      accent:         "#D4A86A",
      accent_dim:     "#9B7840",
      text:           "#FFFFFF",
    },
  },
  {
    id: "modern-blush",
    name: "Modern Blush",
    description: "Weiß-Salbei-Rosé — moderne, zarte Hochzeit",
    swatch: ["#F8F1EC", "#2D3E36", "#C9A8A0", "#8FA89C"],
    colors: {
      bg_top:         "#F8F1EC",
      bg_bottom:      "#E8D9CF",
      sidebar_bg:     "#2D3E36",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#9CB0A6",
      logo_circle:    "#FFFFFF",
      logo_text:      "#2D3E36",
      panel_bg:       "#1E2A24",
      panel_border:   "#8FA89C",
      polaroid_frame: "#FFFFFF",
      polaroid_pin:   "#B26E5E",
      live_bg:        "#1B2520",
      live_outer:     "#8FA89C",
      live_inner:     "#C9A8A0",
      accent:         "#C9A8A0",
      accent_dim:     "#9C7E76",
      text:           "#FFFFFF",
    },
  },
  {
    id: "royal-night",
    name: "Royal Night",
    description: "Navy mit Gold — Gala, Abendveranstaltung",
    swatch: ["#1E2A45", "#0A1224", "#D4AF37", "#F5F0DD"],
    colors: {
      bg_top:         "#1E2A45",
      bg_bottom:      "#0E1729",
      sidebar_bg:     "#0A1224",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#6B7A99",
      logo_circle:    "#1A2540",
      logo_text:      "#D4AF37",
      panel_bg:       "#050913",
      panel_border:   "#D4AF37",
      polaroid_frame: "#F5F0DD",
      polaroid_pin:   "#D4AF37",
      live_bg:        "#050913",
      live_outer:     "#1F3358",
      live_inner:     "#D4AF37",
      accent:         "#D4AF37",
      accent_dim:     "#8B7028",
      text:           "#FFFFFF",
    },
  },
  {
    id: "forest",
    name: "Forest",
    description: "Salbei-Creme-Holz — Boho, Outdoor",
    swatch: ["#DDD7C5", "#2E3D28", "#8AA86E", "#B8794D"],
    colors: {
      bg_top:         "#DDD7C5",
      bg_bottom:      "#B8B89C",
      sidebar_bg:     "#2E3D28",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#95A88A",
      logo_circle:    "#F0EBD8",
      logo_text:      "#2E3D28",
      panel_bg:       "#1A2418",
      panel_border:   "#5A6E48",
      polaroid_frame: "#F0EBD8",
      polaroid_pin:   "#B8794D",
      live_bg:        "#1A2418",
      live_outer:     "#4A5E3C",
      live_inner:     "#8AA86E",
      accent:         "#8AA86E",
      accent_dim:     "#5A6E48",
      text:           "#FFFFFF",
    },
  },
  {
    id: "sunset",
    name: "Sunset",
    description: "Korall-Pfirsich-Burgund — Sommer, warm",
    swatch: ["#FFD4B8", "#6B2737", "#E8765A", "#2D5050"],
    colors: {
      bg_top:         "#FFD4B8",
      bg_bottom:      "#E89A7A",
      sidebar_bg:     "#6B2737",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#B58A95",
      logo_circle:    "#FFE9D6",
      logo_text:      "#6B2737",
      panel_bg:       "#3D1822",
      panel_border:   "#B83C56",
      polaroid_frame: "#FFE9D6",
      polaroid_pin:   "#2D5050",
      live_bg:        "#3D1822",
      live_outer:     "#B83C56",
      live_inner:     "#E8765A",
      accent:         "#E8765A",
      accent_dim:     "#A04A38",
      text:           "#FFFFFF",
    },
  },
  {
    id: "monochrome",
    name: "Monochrome",
    description: "Schwarz-Weiß — Business, minimalistisch",
    swatch: ["#F5F5F5", "#1A1A1A", "#3A3A3A", "#B0B0B0"],
    colors: {
      bg_top:         "#F5F5F5",
      bg_bottom:      "#E0E0E0",
      sidebar_bg:     "#1A1A1A",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#888888",
      logo_circle:    "#FFFFFF",
      logo_text:      "#1A1A1A",
      panel_bg:       "#0E0E0E",
      panel_border:   "#555555",
      polaroid_frame: "#FFFFFF",
      polaroid_pin:   "#B0B0B0",
      live_bg:        "#0E0E0E",
      live_outer:     "#3A3A3A",
      live_inner:     "#999999",
      accent:         "#2D2D2D",
      accent_dim:     "#1A1A1A",
      text:           "#FFFFFF",
    },
  },
  {
    id: "berry",
    name: "Berry",
    description: "Burgund-Rosé-Creme — romantisch",
    swatch: ["#F2DDD9", "#5C1F30", "#B5485E", "#FAEAE5"],
    colors: {
      bg_top:         "#F2DDD9",
      bg_bottom:      "#D9A8AC",
      sidebar_bg:     "#5C1F30",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#B08890",
      logo_circle:    "#FAEAE5",
      logo_text:      "#5C1F30",
      panel_bg:       "#2B0E18",
      panel_border:   "#8A2540",
      polaroid_frame: "#FAEAE5",
      polaroid_pin:   "#2D4A3E",
      live_bg:        "#2B0E18",
      live_outer:     "#8A2540",
      live_inner:     "#B5485E",
      accent:         "#B5485E",
      accent_dim:     "#6E2A3A",
      text:           "#FFFFFF",
    },
  },
  {
    id: "neon-night",
    name: "Neon Night",
    description: "Schwarz-Pink-Cyan — Party, Geburtstag",
    swatch: ["#1A0A20", "#FF1F8A", "#1FE0E0", "#050308"],
    colors: {
      bg_top:         "#1A0A20",
      bg_bottom:      "#0A0612",
      sidebar_bg:     "#050308",
      sidebar_text:   "#FFFFFF",
      sidebar_dim:    "#6A4A7A",
      logo_circle:    "#1A0A20",
      logo_text:      "#FF1F8A",
      panel_bg:       "#050308",
      panel_border:   "#FF1F8A",
      polaroid_frame: "#1A1230",
      polaroid_pin:   "#1FE0E0",
      live_bg:        "#050308",
      live_outer:     "#2E0A48",
      live_inner:     "#FF1F8A",
      accent:         "#FF1F8A",
      accent_dim:     "#B0145E",
      text:           "#FFFFFF",
    },
  },
];

export const DEFAULT_PRESET_ID = "vintage-cream";

export const findActivePreset = (
  current: Record<string, string>,
): ThemePreset | null => {
  for (const p of THEME_PRESETS) {
    let match = true;
    for (const k of Object.keys(p.colors)) {
      const a = (current[k] ?? "").toUpperCase();
      const b = p.colors[k].toUpperCase();
      if (a !== b) { match = false; break; }
    }
    if (match) return p;
  }
  return null;
};
