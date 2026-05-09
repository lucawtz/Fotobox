import { useEffect, useState, useRef, DragEvent } from "react";
import {
  Stack,
  Box,
  Button,
  Typography,
  Snackbar,
  Alert,
  CircularProgress,
} from "@mui/material";
import ImageRoundedIcon from "@mui/icons-material/ImageRounded";
import PaletteRoundedIcon from "@mui/icons-material/PaletteRounded";
import CloudUploadRoundedIcon from "@mui/icons-material/CloudUploadRounded";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import RestartAltRoundedIcon from "@mui/icons-material/RestartAltRounded";
import { api, ThemeColors } from "../../api";
import SettingsCard from "./SettingsCard";

// Defaults müssen mit config.py / ui.py übereinstimmen — sonst sieht ein
// frischer Mieter, der noch nichts gespeichert hat, andere Farben hier als
// auf der Box. Wenn sich die Defaults dort ändern: hier nachziehen.
const DEFAULT_THEME: Record<string, string> = {
  bg_top:       "#D5BB99",
  bg_bottom:    "#B89A75",
  sidebar_bg:   "#3D2818",
  accent:       "#D4A86A",
  live_outer:   "#5A3A1C",
  polaroid_pin: "#C24838",
};

const COLOR_FIELDS: { key: keyof typeof DEFAULT_THEME; label: string; hint: string }[] = [
  { key: "bg_top",       label: "Hintergrund oben",  hint: "Heller Verlaufsstart" },
  { key: "bg_bottom",    label: "Hintergrund unten", hint: "Dunkler Verlaufsende" },
  { key: "sidebar_bg",   label: "Sidebar",            hint: "Linkes Panel" },
  { key: "accent",       label: "Akzent",             hint: "Generischer Goldton" },
  { key: "live_outer",   label: "Live-Rahmen",        hint: "Rahmen ums Live-Bild" },
  { key: "polaroid_pin", label: "Polaroid-Pin",       hint: "Stecknadel oben" },
];

const normalizeHex = (raw: unknown, fallback: string): string => {
  if (typeof raw !== "string") return fallback;
  const v = raw.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return v.toUpperCase();
  return fallback;
};

export default function AdminBranding() {
  // Logo-Section
  const [busy, setBusy] = useState(false);
  const [hasLogo, setHasLogo] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Theme-Section
  const [theme, setTheme] = useState<Record<string, string>>(DEFAULT_THEME);
  const [savedTheme, setSavedTheme] = useState<Record<string, string>>(DEFAULT_THEME);
  const [themeBusy, setThemeBusy] = useState(false);

  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    api.admin.config.get().then((c) => {
      setHasLogo(c.has_logo);
      if (c.has_logo) setPreviewUrl(api.logoUrl());

      const incoming: Record<string, string> = {};
      const t = (c.theme as ThemeColors | undefined) ?? {};
      for (const f of COLOR_FIELDS) {
        incoming[f.key] = normalizeHex(t[f.key], DEFAULT_THEME[f.key]);
      }
      setTheme(incoming);
      setSavedTheme(incoming);
    });
  }, []);

  const upload = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      setToast({ severity: "error", msg: "Nur Bilddateien werden akzeptiert" });
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setToast({ severity: "error", msg: "Datei zu groß (max. 8 MB)" });
      return;
    }
    setBusy(true);
    try {
      const r = await api.admin.uploadLogo(file);
      if (!r.ok) throw new Error(r.error ?? "Upload fehlgeschlagen");
      setHasLogo(true);
      setPreviewUrl(api.logoUrl());
      setToast({ severity: "success", msg: "Logo hochgeladen" });
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  };

  const themeDirty = COLOR_FIELDS.some((f) => theme[f.key] !== savedTheme[f.key]);

  const saveTheme = async () => {
    setThemeBusy(true);
    try {
      await api.admin.config.save({ theme: { ...theme } });
      setSavedTheme({ ...theme });
      setToast({ severity: "success", msg: "Farbschema gespeichert" });
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setThemeBusy(false);
    }
  };

  const resetTheme = () => setTheme({ ...DEFAULT_THEME });

  return (
    <>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            Erscheinungsbild
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Logo und Farbschema des Homescreens
          </Typography>
        </Box>

        <SettingsCard
          icon={<ImageRoundedIcon />}
          title="Logo"
          description="PNG empfohlen, transparent. Erscheint im Cream-Kreis links oben."
        >
          <Box
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            sx={{
              cursor: "pointer",
              borderRadius: 3,
              border: "2px dashed",
              borderColor: dragOver ? "primary.main" : "divider",
              bgcolor: dragOver ? "#e8f0fe" : "grey.50",
              transition: "all .15s",
              p: { xs: 3, sm: 4 },
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              textAlign: "center",
              "&:hover": { bgcolor: dragOver ? "#e8f0fe" : "grey.100" },
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload(f);
                e.target.value = "";
              }}
            />

            {busy ? (
              <CircularProgress />
            ) : previewUrl ? (
              <Box
                component="img"
                src={previewUrl}
                alt="Logo"
                sx={{
                  maxWidth: { xs: 180, sm: 220 },
                  maxHeight: 140,
                  objectFit: "contain",
                  filter: "drop-shadow(0 2px 8px rgba(60,64,67,0.15))",
                }}
              />
            ) : (
              <Box
                sx={{
                  width: 64, height: 64, borderRadius: "50%",
                  bgcolor: "#e8f0fe",
                  display: "grid", placeItems: "center",
                  color: "primary.main",
                }}
              >
                <CloudUploadRoundedIcon fontSize="large" />
              </Box>
            )}

            <Box>
              <Typography variant="body2" sx={{ color: "text.primary", fontWeight: 500 }}>
                {hasLogo ? "Klicken oder Datei hier ablegen, um zu ersetzen" : "Klicken oder Datei hier ablegen"}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                PNG, JPG, WebP oder SVG · max. 8 MB
              </Typography>
            </Box>

            {hasLogo && !busy && (
              <Stack direction="row" alignItems="center" spacing={0.75} sx={{ color: "success.main" }}>
                <CheckCircleRoundedIcon fontSize="small" />
                <Typography variant="caption">Aktuelles Logo aktiv</Typography>
              </Stack>
            )}
          </Box>

          <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
            <Button
              variant="outlined"
              startIcon={<CloudUploadRoundedIcon />}
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              Datei auswählen
            </Button>
          </Box>
        </SettingsCard>

        <SettingsCard
          icon={<PaletteRoundedIcon />}
          title="Farbschema"
          description="Farben für Hintergrund, Sidebar und Akzente. Änderungen sind nach 1 Sekunde live auf der Box."
        >
          <Box
            sx={{
              display: "grid",
              // Auf schmalen Screens 1 Spalte, damit lange Labels wie
              // "Hintergrund unten" oder "Polaroid-Pin" nicht abgeschnitten
              // werden. Ab sm 2 Spalten, ab md 3 Spalten.
              gridTemplateColumns: {
                xs: "1fr",
                sm: "repeat(2, 1fr)",
                md: "repeat(3, 1fr)",
              },
              gap: { xs: 1.25, sm: 2 },
            }}
          >
            {COLOR_FIELDS.map((f) => (
              <Box
                key={f.key}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.5,
                  p: 1.25,
                  minWidth: 0,
                  borderRadius: 2,
                  border: "1px solid",
                  borderColor: "divider",
                  bgcolor: "grey.50",
                }}
              >
                <Box
                  component="label"
                  sx={{
                    position: "relative",
                    width: 44, height: 44,
                    borderRadius: "50%",
                    border: "2px solid",
                    borderColor: "divider",
                    overflow: "hidden",
                    flexShrink: 0,
                    cursor: "pointer",
                    bgcolor: theme[f.key] ?? DEFAULT_THEME[f.key],
                    "&:hover": { borderColor: "primary.main" },
                  }}
                >
                  <input
                    type="color"
                    value={theme[f.key] ?? DEFAULT_THEME[f.key]}
                    onChange={(e) =>
                      setTheme((t) => ({ ...t, [f.key]: e.target.value.toUpperCase() }))
                    }
                    style={{
                      position: "absolute",
                      inset: 0,
                      opacity: 0,
                      cursor: "pointer",
                      width: "100%",
                      height: "100%",
                    }}
                  />
                </Box>
                <Box sx={{ minWidth: 0, flex: 1, overflow: "hidden" }}>
                  <Typography
                    variant="body2"
                    sx={{
                      fontWeight: 600,
                      lineHeight: 1.2,
                      // Lange Labels duerfen umbrechen statt abgeschnitten zu werden.
                      whiteSpace: "normal",
                      overflowWrap: "break-word",
                    }}
                  >
                    {f.label}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{
                      display: "block",
                      lineHeight: 1.2,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {(theme[f.key] ?? DEFAULT_THEME[f.key]).toUpperCase()}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Box>

          <Box
            sx={{
              mt: 2.5,
              display: "flex",
              justifyContent: { xs: "stretch", sm: "flex-end" },
              gap: 1.5,
            }}
          >
            <Button
              startIcon={<RestartAltRoundedIcon />}
              onClick={resetTheme}
              color="inherit"
              sx={{ flex: { xs: 1, sm: "0 0 auto" } }}
            >
              Standard
            </Button>
            <Button
              variant="contained"
              onClick={saveTheme}
              disabled={!themeDirty || themeBusy}
              sx={{ flex: { xs: 1, sm: "0 0 auto" } }}
            >
              {themeBusy ? "Speichere…" : "Speichern"}
            </Button>
          </Box>
        </SettingsCard>
      </Stack>

      <Snackbar
        open={!!toast}
        autoHideDuration={2400}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity={toast?.severity ?? "info"} variant="filled" onClose={() => setToast(null)}>
          {toast?.msg}
        </Alert>
      </Snackbar>
    </>
  );
}
