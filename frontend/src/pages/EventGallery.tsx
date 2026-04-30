import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Fade,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import DownloadForOfflineRoundedIcon from "@mui/icons-material/DownloadForOfflineRounded";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import { api, Photo } from "../api";
import PhotoTile from "../components/PhotoTile";

const POLL_MS = 8000;

const formatDate = (iso: string): string => {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", {
    day: "numeric", month: "long", year: "numeric",
  });
};

export default function EventGallery() {
  const { folder } = useParams<{ folder: string }>();
  const navigate = useNavigate();

  const [photos, setPhotos] = useState<Photo[]>([]);
  const [eventDisplay, setEventDisplay] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [active, setActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const knownCount = useRef(0);

  const load = useCallback(async () => {
    if (!folder) return;
    try {
      const [list, evRes] = await Promise.all([
        api.list(folder),
        api.events(),
      ]);
      setPhotos(list.photos);
      knownCount.current = list.count;
      const meta = evRes.events.find((e) => e.folder === folder);
      if (meta) {
        setEventDisplay(meta.display);
        setEventDate(meta.date);
        setActive(meta.active);
      } else {
        setEventDisplay(folder);
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [folder]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    if (!folder) return;
    const id = setInterval(async () => {
      try {
        const r = await api.count(folder);
        if (r.count !== knownCount.current) load();
      } catch { /* ignore */ }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [folder, load]);

  const handleDownload = () => {
    if (!folder || photos.length === 0) return;
    window.location.href = api.zipUrl(folder);
  };

  const subtitle = loading ? "Lade…"
                 : `${photos.length} Foto${photos.length === 1 ? "" : "s"}${eventDate ? ` · ${formatDate(eventDate)}` : ""}`;

  return (
    <>
      {/* Eigene TopBar — mit Back-Button + ZIP/Refresh-Actions */}
      <Box
        component="header"
        sx={{
          position: "sticky", top: 0, zIndex: 10,
          bgcolor: "background.paper",
          borderBottom: "1px solid",
          borderColor: "divider",
          px: { xs: 1.5, sm: 2.5 },
          py: { xs: 1, sm: 1.25 },
          display: "flex",
          alignItems: "center",
          gap: 1,
          minHeight: { xs: 64, sm: 72 },
        }}
      >
        <IconButton onClick={() => navigate("/")}>
          <ArrowBackRoundedIcon />
        </IconButton>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 0 }}>
            <Typography
              noWrap
              variant="h6"
              sx={{
                fontSize: { xs: "1.05rem", sm: "1.2rem" },
                fontWeight: 500,
                color: "text.primary",
                lineHeight: 1.15,
                minWidth: 0,
              }}
            >
              {eventDisplay || "Event"}
            </Typography>
            {active && (
              <Chip
                label="Aktiv"
                size="small"
                color="primary"
                variant="outlined"
                sx={{ height: 22, fontSize: ".7rem", fontWeight: 500 }}
              />
            )}
          </Stack>
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", lineHeight: 1.2 }}>
            {subtitle}
          </Typography>
        </Box>

        {photos.length > 0 && (
          <>
            <Tooltip title="Als ZIP herunterladen">
              <Button
                onClick={handleDownload}
                startIcon={<DownloadForOfflineRoundedIcon />}
                variant="contained"
                size="small"
                sx={{ display: { xs: "none", sm: "inline-flex" }, px: 2.25 }}
              >
                ZIP
              </Button>
            </Tooltip>
            <IconButton
              onClick={handleDownload}
              sx={{ display: { xs: "inline-flex", sm: "none" }, color: "primary.main" }}
              aria-label="ZIP herunterladen"
            >
              <DownloadForOfflineRoundedIcon />
            </IconButton>
          </>
        )}

        <Tooltip title="Aktualisieren">
          <IconButton onClick={load}>
            <RefreshRoundedIcon />
          </IconButton>
        </Tooltip>
      </Box>

      <Container maxWidth="xl" disableGutters sx={{ pb: 6 }}>
        {loading && photos.length === 0 && (
          <Stack alignItems="center" sx={{ pt: 12 }}>
            <CircularProgress size={28} />
          </Stack>
        )}

        {!loading && photos.length === 0 && !error && (
          <Fade in>
            <Stack
              alignItems="center"
              justifyContent="center"
              spacing={2.5}
              sx={{ minHeight: "60dvh", textAlign: "center", color: "text.secondary", px: 3 }}
            >
              <Box
                sx={{
                  width: 96, height: 96, borderRadius: "50%",
                  display: "grid", placeItems: "center",
                  bgcolor: "grey.100",
                }}
              >
                <PhotoCameraRoundedIcon sx={{ fontSize: 44, color: "primary.main" }} />
              </Box>
              <Typography variant="h5" sx={{ color: "text.primary", fontWeight: 500 }}>
                Keine Fotos in diesem Event
              </Typography>
            </Stack>
          </Fade>
        )}

        {error && (
          <Stack alignItems="center" sx={{ pt: 6 }}>
            <Chip label={`Fehler: ${error}`} color="error" variant="outlined" />
          </Stack>
        )}

        {photos.length > 0 && (
          <Box
            sx={{
              display: "grid",
              gap: { xs: 0.5, sm: 1, md: 1.25 },
              p: { xs: 0.5, sm: 1, md: 1.5 },
              gridTemplateColumns: {
                xs: "repeat(3, 1fr)",
                sm: "repeat(4, 1fr)",
                md: "repeat(5, 1fr)",
                lg: "repeat(6, 1fr)",
                xl: "repeat(8, 1fr)",
              },
            }}
          >
            {photos.map((p) => (
              <PhotoTile key={`${p.event}/${p.filename}`} photo={p} />
            ))}
          </Box>
        )}
      </Container>
    </>
  );
}
