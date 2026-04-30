import { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Container,
  Fade,
  Stack,
  Typography,
  CircularProgress,
  Chip,
  Button,
  Tooltip,
} from "@mui/material";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import DownloadForOfflineRoundedIcon from "@mui/icons-material/DownloadForOfflineRounded";
import { api, EventInfo, Photo } from "../api";
import TopBar from "../components/TopBar";
import PhotoTile from "../components/PhotoTile";

const POLL_MS = 8000;
const ALL = "__all__";

export default function Gallery() {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [allEvents, setAllEvents] = useState<EventInfo[]>([]);
  const [eventName, setEventName] = useState("Fotobox");
  const [activeEvent, setActiveEvent] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>(ALL);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const knownCount = useRef(0);

  const load = useCallback(async (filt: string) => {
    try {
      const evReq = api.events();
      const photosReq = api.list(filt === ALL ? null : filt);
      const [evs, ph] = await Promise.all([evReq, photosReq]);
      setAllEvents(evs.events);
      setActiveEvent(evs.active);
      setEventName(evs.event_name);
      setPhotos(ph.photos);
      knownCount.current = ph.count;
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    load(filter);
  }, [filter, load]);

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const r = await api.count(filter === ALL ? null : filter);
        if (r.count !== knownCount.current) load(filter);
      } catch { /* ignore */ }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [filter, load]);

  const subtitle = loading
    ? "Lade…"
    : `${photos.length} Foto${photos.length === 1 ? "" : "s"}`;

  const showChips = allEvents.length > 1;

  const downloadLabel = filter === ALL ? "Alle herunterladen" : "Event herunterladen";
  const handleDownload = () => {
    window.location.href = api.zipUrl(filter === ALL ? null : filter);
  };

  const desktopAction = photos.length > 0 && (
    <Button
      onClick={handleDownload}
      startIcon={<DownloadForOfflineRoundedIcon />}
      variant="contained"
      size="small"
      sx={{
        display: { xs: "none", sm: "inline-flex" },
        px: 2.25,
      }}
    >
      ZIP
    </Button>
  );
  const mobileAction = photos.length > 0 && (
    <Tooltip title={downloadLabel}>
      <span style={{ display: "inline-flex" }}>
        <Box
          component="button"
          onClick={handleDownload}
          sx={{
            display: { xs: "inline-flex", sm: "none" },
            background: "transparent",
            border: 0,
            cursor: "pointer",
            color: "primary.main",
            p: 1,
            borderRadius: "50%",
            "&:hover": { bgcolor: "rgba(26,115,232,0.08)" },
          }}
          aria-label={downloadLabel}
        >
          <DownloadForOfflineRoundedIcon />
        </Box>
      </span>
    </Tooltip>
  );

  return (
    <>
      <TopBar
        title={eventName}
        subtitle={subtitle}
        onRefresh={() => load(filter)}
        actions={<>{desktopAction}{mobileAction}</>}
      />

      {showChips && (
        <Box
          sx={{
            position: "sticky",
            top: { xs: 64, sm: 72 },
            zIndex: 5,
            bgcolor: "background.paper",
            borderBottom: "1px solid",
            borderColor: "divider",
            px: { xs: 1.5, sm: 2 },
            py: 1.25,
            display: "flex",
            gap: 0.75,
            overflowX: "auto",
            scrollbarWidth: "thin",
            "&::-webkit-scrollbar": { height: 4 },
            "&::-webkit-scrollbar-thumb": { background: "#dadce0", borderRadius: 2 },
          }}
        >
          <Chip
            label={`Alle · ${allEvents.reduce((s, e) => s + e.count, 0)}`}
            onClick={() => setFilter(ALL)}
            color={filter === ALL ? "primary" : "default"}
            variant={filter === ALL ? "filled" : "outlined"}
            sx={{ fontWeight: 500, flexShrink: 0 }}
          />
          {allEvents.map((ev) => (
            <Chip
              key={ev.folder}
              label={`${ev.display}${ev.active ? " · live" : ""} · ${ev.count}`}
              onClick={() => setFilter(ev.folder)}
              color={filter === ev.folder ? "primary" : "default"}
              variant={filter === ev.folder ? "filled" : "outlined"}
              sx={{
                fontWeight: 500,
                flexShrink: 0,
                ...(ev.active && filter !== ev.folder && {
                  borderColor: "primary.main",
                  color: "primary.main",
                }),
              }}
            />
          ))}
        </Box>
      )}

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
              sx={{ minHeight: "70dvh", textAlign: "center", color: "text.secondary", px: 3 }}
            >
              <Box
                sx={{
                  width: 96,
                  height: 96,
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  bgcolor: "grey.100",
                }}
              >
                <PhotoCameraRoundedIcon sx={{ fontSize: 44, color: "primary.main" }} />
              </Box>
              <Typography variant="h5" sx={{ color: "text.primary", fontWeight: 500 }}>
                {filter === ALL ? "Noch keine Fotos" : "Keine Fotos in diesem Event"}
              </Typography>
              <Typography variant="body2" sx={{ maxWidth: 320 }}>
                {filter === ALL
                  ? "Drück auf den Auslöser an der Fotobox — dein erstes Foto erscheint hier automatisch."
                  : "Wechsle zu einem anderen Event über die Chips oben."}
              </Typography>
              {/* activeEvent Hinweis */}
              {filter === ALL && activeEvent && (
                <Typography variant="caption" sx={{ color: "text.disabled" }}>
                  aktiver Ordner: {activeEvent}
                </Typography>
              )}
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
