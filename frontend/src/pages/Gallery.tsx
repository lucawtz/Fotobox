import { useCallback, useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Box,
  Container,
  Fade,
  Stack,
  Typography,
  CircularProgress,
  Chip,
  Paper,
} from "@mui/material";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import FolderRoundedIcon from "@mui/icons-material/FolderRounded";
import FiberManualRecordRoundedIcon from "@mui/icons-material/FiberManualRecordRounded";
import { api, EventInfo } from "../api";
import TopBar from "../components/TopBar";

const POLL_MS = 8000;

const formatDate = (iso: string): string => {
  // "2026-04-30" → "30. April 2026"
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", {
    day: "numeric", month: "long", year: "numeric",
  });
};

export default function Gallery() {
  const [items, setItems] = useState<EventInfo[]>([]);
  const [eventName, setEventName] = useState("Fotobox");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.events();
      setItems(r.events);
      setEventName(r.event_name);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const totalPhotos = items.reduce((s, e) => s + e.count, 0);
  const subtitle = loading
    ? "Lade…"
    : `${items.length} Event${items.length === 1 ? "" : "s"} · ${totalPhotos} Foto${totalPhotos === 1 ? "" : "s"}`;

  return (
    <>
      <TopBar title={eventName} subtitle={subtitle} onRefresh={load} />

      <Container maxWidth="xl" sx={{ py: { xs: 2, sm: 3 } }}>
        {loading && items.length === 0 && (
          <Stack alignItems="center" sx={{ pt: 12 }}>
            <CircularProgress size={28} />
          </Stack>
        )}

        {!loading && items.length === 0 && !error && (
          <Fade in>
            <Stack
              alignItems="center"
              justifyContent="center"
              spacing={2.5}
              sx={{ minHeight: "70dvh", textAlign: "center", color: "text.secondary", px: 3 }}
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
                Noch keine Fotos
              </Typography>
              <Typography variant="body2" sx={{ maxWidth: 320 }}>
                Drück auf den Auslöser an der Fotobox — dein erstes Foto erscheint
                hier automatisch.
              </Typography>
            </Stack>
          </Fade>
        )}

        {error && (
          <Stack alignItems="center" sx={{ pt: 6 }}>
            <Chip label={`Fehler: ${error}`} color="error" variant="outlined" />
          </Stack>
        )}

        {items.length > 0 && (
          <Box
            sx={{
              display: "grid",
              gap: { xs: 1.5, sm: 2 },
              gridTemplateColumns: {
                xs: "repeat(2, 1fr)",
                sm: "repeat(3, 1fr)",
                md: "repeat(4, 1fr)",
                lg: "repeat(5, 1fr)",
              },
            }}
          >
            {items.map((ev) => (
              <EventCard key={ev.folder} ev={ev} />
            ))}
          </Box>
        )}
      </Container>
    </>
  );
}

function EventCard({ ev }: { ev: EventInfo }) {
  return (
    <Paper
      elevation={0}
      component={RouterLink}
      to={`/event/${encodeURIComponent(ev.folder)}`}
      sx={{
        position: "relative",
        display: "block",
        textDecoration: "none",
        color: "inherit",
        borderRadius: 3,
        overflow: "hidden",
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        transition: "box-shadow .15s, transform .15s",
        WebkitTapHighlightColor: "transparent",
        "&:hover": {
          boxShadow: "0 1px 3px rgba(60,64,67,.12), 0 4px 12px rgba(60,64,67,.10)",
          transform: { sm: "translateY(-2px)" },
        },
      }}
    >
      <Box sx={{ position: "relative", aspectRatio: "4 / 3", bgcolor: "grey.100" }}>
        <Box
          component="img"
          src={api.thumbUrl({ event: ev.folder, filename: ev.cover })}
          alt={ev.display}
          loading="lazy"
          decoding="async"
          sx={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
        {ev.active && (
          <Chip
            icon={<FiberManualRecordRoundedIcon sx={{ fontSize: "0.6rem !important", color: "#ea4335 !important" }} />}
            label="Aktiv"
            size="small"
            sx={{
              position: "absolute",
              top: 8, left: 8,
              bgcolor: "rgba(255,255,255,0.95)",
              backdropFilter: "blur(6px)",
              color: "text.primary",
              fontWeight: 500,
              fontSize: ".7rem",
              height: 24,
            }}
          />
        )}
        <Box
          sx={{
            position: "absolute",
            right: 8, bottom: 8,
            bgcolor: "rgba(0,0,0,0.55)",
            color: "#fff",
            borderRadius: 1.5,
            px: 1, py: 0.25,
            fontSize: ".72rem",
            fontWeight: 500,
            backdropFilter: "blur(4px)",
          }}
        >
          {ev.count}
        </Box>
      </Box>

      <Stack
        direction="row"
        spacing={1.25}
        alignItems="flex-start"
        sx={{ p: { xs: 1.25, sm: 1.5 } }}
      >
        <FolderRoundedIcon sx={{ color: "primary.main", fontSize: 22, mt: "1px" }} />
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            noWrap
            sx={{ fontWeight: 500, fontSize: ".95rem", color: "text.primary" }}
          >
            {ev.display}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", display: "block", lineHeight: 1.3 }}
          >
            {formatDate(ev.date)}
          </Typography>
        </Box>
      </Stack>
    </Paper>
  );
}
