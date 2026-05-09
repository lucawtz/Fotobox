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
import { api, EventInfo, formatDate } from "../api";
import TopBar from "../components/TopBar";
import ViewToggle, { useGalleryView } from "../components/ViewToggle";

const POLL_MS = 8000;

export default function Gallery() {
  const [items, setItems] = useState<EventInfo[]>([]);
  const [eventName, setEventName] = useState("Fotobox");
  const [maxAgeDays, setMaxAgeDays] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.events();
      setItems(r.events);
      setEventName(r.event_name);
      setMaxAgeDays(r.photo_max_age_days || 0);
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

  const [view, setView] = useGalleryView("events", "grid");

  return (
    <>
      <TopBar
        title={eventName}
        subtitle={subtitle}
        onRefresh={load}
        actions={items.length > 0 ? <ViewToggle value={view} onChange={setView} /> : undefined}
      />

      <Container
        maxWidth="xl"
        sx={{
          py: { xs: 1.5, sm: 3 },
          px: { xs: 1.25, sm: 3 },
          pb: "calc(var(--sa-bottom) + 24px)",
        }}
      >
        {maxAgeDays > 0 && items.length > 0 && (
          <Typography
            variant="caption"
            sx={{
              display: "block",
              textAlign: "center",
              color: "text.secondary",
              mb: { xs: 1.25, sm: 2 },
              fontSize: { xs: ".72rem", sm: ".78rem" },
            }}
          >
            Fotos werden nach {maxAgeDays} Tag{maxAgeDays === 1 ? "" : "en"} automatisch gelöscht
          </Typography>
        )}

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

        {items.length > 0 && view === "grid" && (
          <Box
            sx={{
              display: "grid",
              gap: { xs: 1.25, sm: 2 },
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

        {items.length > 0 && view === "list" && (
          <Paper
            elevation={0}
            sx={{
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1.5,
              overflow: "hidden",
              bgcolor: "background.paper",
            }}
          >
            {items.map((ev, i) => (
              <EventListRow key={ev.folder} ev={ev} divider={i < items.length - 1} />
            ))}
          </Paper>
        )}
      </Container>
    </>
  );
}

function EventListRow({ ev, divider }: { ev: EventInfo; divider: boolean }) {
  return (
    <Box
      component={RouterLink}
      to={`/event/${encodeURIComponent(ev.folder)}`}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: { xs: 1.25, sm: 2 },
        px: { xs: 1.25, sm: 2 },
        py: { xs: 1, sm: 1.25 },
        textDecoration: "none",
        color: "inherit",
        borderBottom: divider ? "1px solid" : 0,
        borderColor: "divider",
        WebkitTapHighlightColor: "transparent",
        transition: "background-color .12s",
        "&:hover": { bgcolor: "grey.50" },
      }}
    >
      <Box
        sx={{
          width: { xs: 48, sm: 56 },
          height: { xs: 48, sm: 56 },
          borderRadius: 1,
          overflow: "hidden",
          bgcolor: "grey.100",
          flexShrink: 0,
          position: "relative",
        }}
      >
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
      </Box>

      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
          <Typography
            noWrap
            sx={{
              fontWeight: 500,
              fontSize: { xs: ".9rem", sm: "1rem" },
              color: "text.primary",
              lineHeight: 1.3,
              minWidth: 0,
            }}
          >
            {ev.display}
          </Typography>
          {ev.active && (
            <Chip
              icon={<FiberManualRecordRoundedIcon sx={{ fontSize: "0.55rem !important", color: "#ea4335 !important" }} />}
              label="Aktiv"
              size="small"
              sx={{
                height: 18,
                fontSize: ".65rem",
                fontWeight: 500,
                flexShrink: 0,
              }}
            />
          )}
        </Stack>
        <Typography
          variant="caption"
          noWrap
          sx={{
            color: "text.secondary",
            display: "block",
            lineHeight: 1.3,
            fontSize: { xs: ".7rem", sm: ".75rem" },
          }}
        >
          {formatDate(ev.date)}
        </Typography>
      </Box>

      <Typography
        variant="body2"
        sx={{
          color: "text.secondary",
          fontVariantNumeric: "tabular-nums",
          fontSize: { xs: ".8rem", sm: ".85rem" },
          flexShrink: 0,
        }}
      >
        {ev.count} Foto{ev.count === 1 ? "" : "s"}
      </Typography>
    </Box>
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
        borderRadius: 1.5,
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
            borderRadius: 1,
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
        spacing={{ xs: 1, sm: 1.25 }}
        alignItems="flex-start"
        sx={{ p: { xs: 1, sm: 1.5 } }}
      >
        <FolderRoundedIcon
          sx={{ color: "primary.main", fontSize: { xs: 18, sm: 22 }, mt: "2px", flexShrink: 0 }}
        />
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            noWrap
            sx={{
              fontWeight: 500,
              fontSize: { xs: ".85rem", sm: ".95rem" },
              color: "text.primary",
              lineHeight: 1.3,
            }}
          >
            {ev.display}
          </Typography>
          <Typography
            variant="caption"
            noWrap
            sx={{
              color: "text.secondary",
              display: "block",
              lineHeight: 1.3,
              fontSize: { xs: ".7rem", sm: ".75rem" },
            }}
          >
            {formatDate(ev.date)}
          </Typography>
        </Box>
      </Stack>
    </Paper>
  );
}
