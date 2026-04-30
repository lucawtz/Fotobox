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
import CloudUploadRoundedIcon from "@mui/icons-material/CloudUploadRounded";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import { api } from "../../api";
import SettingsCard from "./SettingsCard";

export default function AdminBranding() {
  const [busy, setBusy] = useState(false);
  const [hasLogo, setHasLogo] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.admin.config.get().then((c) => {
      setHasLogo(c.has_logo);
      if (c.has_logo) setPreviewUrl(api.logoUrl());
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

  return (
    <>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            Logo
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Eigenes Logo für Homescreen und Foto-Overlay
          </Typography>
        </Box>

        <SettingsCard
          icon={<ImageRoundedIcon />}
          title="Logo-Datei"
          description="PNG empfohlen, transparent. Wird automatisch eingebunden."
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
              accept="image/png,image/jpeg,image/webp,image/svg+xml"
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
