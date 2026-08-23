import { useCallback, useEffect, useRef, useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Fade,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import DownloadForOfflineRoundedIcon from "@mui/icons-material/DownloadForOfflineRounded";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import DeleteForeverRoundedIcon from "@mui/icons-material/DeleteForeverRounded";
import { api, matchesFilter, OwnerLinks as Links, Photo, PhotoFilter, formatDate } from "../api";
import RoleBadge from "../components/RoleBadge";
import { useSessionRole } from "../sessionRole";
import PhotoTile from "../components/PhotoTile";
import ViewToggle, { useGalleryView } from "../components/ViewToggle";
import KindFilter from "../components/KindFilter";
import OwnerLinks from "../components/OwnerLinks";

const POLL_MS = 8000;

export default function EventGallery() {
  const { folder } = useParams<{ folder: string }>();
  const navigate = useNavigate();

  const [photos, setPhotos] = useState<Photo[]>([]);
  const [eventDisplay, setEventDisplay] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [active, setActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [links, setLinks] = useState<Links | null>(null);
  // Bewusst nicht in den localStorage wie die Ansicht: ein gemerkter Filter
  // liesse den Gast beim naechsten Besuch Bilder vermissen, ohne zu sehen
  // warum.
  const [kind, setKind] = useState<PhotoFilter>("alle");
  const knownCount = useRef(0);

  // Nur der Admin raeumt ganze Events weg — der Gastgeber bekommt fremde
  // Ordner ohnehin nicht zu sehen (_may_see_all_events im Galerie-Server).
  const role = useSessionRole();
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [purging, setPurging] = useState(false);
  const [purgeError, setPurgeError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!folder) return;
    try {
      const [list, evRes] = await Promise.all([
        api.list(folder),
        api.events(),
      ]);
      setPhotos(list.photos);
      setLinks(list);
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

  const handlePurge = async () => {
    if (!folder) return;
    setPurging(true); setPurgeError(null);
    try {
      await api.admin.deleteEvent(folder);
      navigate("/", { replace: true });
    } catch (e) {
      setPurgeError(e instanceof Error ? e.message : String(e));
      setPurging(false);
    }
  };

  const counts: Record<PhotoFilter, number> = {
    alle:    photos.filter((p) => matchesFilter(p, "alle")).length,
    collage: photos.filter((p) => matchesFilter(p, "collage")).length,
    single:  photos.filter((p) => matchesFilter(p, "single")).length,
  };
  const hasCollages = counts.collage > 0;
  // Ohne Collagen im Event gibt es nichts zu filtern — dann bleibt es bei der
  // gefalteten Standardansicht, egal was im State steht.
  const shown = photos.filter((p) => matchesFilter(p, hasCollages ? kind : "alle"));

  const handleDownload = () => {
    if (!folder || shown.length === 0) return;
    // Was gefiltert auf dem Schirm steht, kommt auch so aus dem ZIP.
    window.location.href = api.zipUrl(folder, hasCollages ? kind : "alle");
  };

  const subtitle = loading ? "Lade…"
                 : `${shown.length} Bild${shown.length === 1 ? "" : "er"}${eventDate ? ` · ${formatDate(eventDate)}` : ""}`;

  const [view, setView] = useGalleryView("photos", "grid");

  return (
    // Siehe Gallery.tsx: Flex-Spalte ueber die ganze Seite, damit
    // <OwnerLinks> per mt:auto unten andocken kann, ohne dass irgendwo eine
    // Kopfhoehe von Hand gepflegt werden muss.
    <Box sx={{ display: "flex", flexDirection: "column", minHeight: "100dvh" }}>
      {/* Eigene TopBar — mit Back-Button + ZIP/Refresh-Actions */}
      <Box
        component="header"
        sx={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          bgcolor: "background.paper",
          borderBottom: "1px solid",
          borderColor: "divider",
          pt: "var(--sa-top)",
          pl: "var(--sa-left)",
          pr: "var(--sa-right)",
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: { xs: 0.5, sm: 1 },
            px: { xs: 1, sm: 2.5 },
            py: { xs: 0.75, sm: 1.25 },
            minHeight: { xs: 56, sm: 72 },
          }}
        >
          <IconButton onClick={() => navigate("/")} aria-label="Zurück" edge="start">
            <ArrowBackRoundedIcon />
          </IconButton>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
              <Typography
                noWrap
                variant="h6"
                sx={{
                  fontSize: { xs: ".95rem", sm: "1.2rem" },
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
                  sx={{
                    height: { xs: 18, sm: 22 },
                    fontSize: { xs: ".65rem", sm: ".7rem" },
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
                lineHeight: 1.2,
                fontSize: { xs: ".7rem", sm: ".75rem" },
              }}
            >
              {subtitle}
            </Typography>
          </Box>

          {photos.length > 0 && (
            <Box sx={{ display: { xs: "none", sm: "inline-flex" }, flexShrink: 0 }}>
              <ViewToggle value={view} onChange={setView} />
            </Box>
          )}

          {photos.length > 0 && (
            <Tooltip title="Als ZIP herunterladen">
              <Button
                onClick={handleDownload}
                startIcon={<DownloadForOfflineRoundedIcon />}
                variant="contained"
                size="small"
                sx={{
                  px: { xs: 1.5, sm: 2.25 },
                  py: { xs: 0.5, sm: 0.75 },
                  fontSize: { xs: ".8rem", sm: ".85rem" },
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                  "& .MuiButton-startIcon": {
                    mr: { xs: 0.5, sm: 1 },
                  },
                }}
              >
                ZIP
              </Button>
            </Tooltip>
          )}

          {photos.length > 0 && (
            <Box sx={{ display: { xs: "inline-flex", sm: "none" }, flexShrink: 0 }}>
              <ViewToggle value={view} onChange={setView} />
            </Box>
          )}

          <Tooltip title="Aktualisieren">
            <IconButton
              onClick={load}
              aria-label="Aktualisieren"
              sx={{ display: { xs: "none", sm: "inline-flex" } }}
            >
              <RefreshRoundedIcon />
            </IconButton>
          </Tooltip>

          {/* Nur fuer Angemeldete: hier steht der "Event loeschen"-Knopf, da
              muss man sehen, mit welcher Rolle man unterwegs ist. Fuer Gaeste
              bleibt dieser Header unveraendert. */}
          <RoleBadge hideWhenGuest />
        </Box>
      </Box>

      <Container
        maxWidth="xl"
        disableGutters
        sx={{
          pb: "calc(var(--sa-bottom) + 24px)",
          flex: 1,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Eigene Zeile statt in die Kopfleiste: dort draengeln sich schon
            Zurueck, Ansicht, ZIP und Aktualisieren, und drei Filterknoepfe
            mit Zahl passen auf einem Handy nicht mehr daneben. */}
        {hasCollages && (
          <Box
            sx={{
              display: "flex",
              justifyContent: { xs: "flex-start", sm: "center" },
              px: { xs: 1, sm: 1.5 },
              pt: { xs: 1, sm: 1.5 },
              overflowX: "auto",
              "&::-webkit-scrollbar": { display: "none" },
              scrollbarWidth: "none",
            }}
          >
            <KindFilter value={kind} onChange={setKind} counts={counts} />
          </Box>
        )}

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

        {shown.length > 0 && view === "grid" && (
          <Box
            sx={{
              display: "grid",
              gap: { xs: 0.5, sm: 1, md: 1.25 },
              p: { xs: 0.5, sm: 1, md: 1.5 },
              gridTemplateColumns: {
                xs: "repeat(3, minmax(0, 1fr))",
                sm: "repeat(4, minmax(0, 1fr))",
                md: "repeat(5, minmax(0, 1fr))",
                lg: "repeat(6, minmax(0, 1fr))",
                xl: "repeat(8, minmax(0, 1fr))",
              },
            }}
          >
            {shown.map((p) => (
              <PhotoTile key={`${p.event}/${p.filename}`} photo={p} />
            ))}
          </Box>
        )}

        {shown.length > 0 && view === "list" && (
          <Paper
            elevation={0}
            sx={{
              m: { xs: 0.5, sm: 1, md: 1.5 },
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1.5,
              overflow: "hidden",
              bgcolor: "background.paper",
            }}
          >
            {shown.map((p, i) => (
              <PhotoListRow
                key={`${p.event}/${p.filename}`}
                photo={p}
                divider={i < shown.length - 1}
              />
            ))}
          </Paper>
        )}

        {role === "admin" && !loading && photos.length > 0 && (
          <Box sx={{ px: { xs: 1.25, sm: 3 }, pt: 3, display: "flex", justifyContent: "center" }}>
            <Button
              onClick={() => setConfirmPurge(true)}
              startIcon={<DeleteForeverRoundedIcon />}
              color="error"
              variant="outlined"
              size="small"
            >
              Event löschen
            </Button>
          </Box>
        )}

        {!loading && (
          // Container laeuft hier mit disableGutters — Padding deshalb hier.
          // mt:auto dockt den Block bei kurzer Galerie unten an.
          <Box sx={{ px: { xs: 1.25, sm: 3 }, mt: "auto" }}>
            <OwnerLinks links={links} />
          </Box>
        )}
      </Container>

      <Dialog
        open={confirmPurge}
        onClose={purging ? undefined : () => setConfirmPurge(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25, pb: 1 }}>
          <DeleteForeverRoundedIcon color="error" />
          Event löschen?
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              <b>{eventDisplay || folder}</b> mit {photos.length} Foto
              {photos.length === 1 ? "" : "s"} wird endgültig gelöscht. Vorher
              per ZIP sichern, falls du die Bilder noch brauchst.
            </Typography>
            {purgeError && (
              <Alert severity="error" variant="outlined">{purgeError}</Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button
            onClick={() => setConfirmPurge(false)}
            disabled={purging}
            color="inherit"
            sx={{ flex: 1 }}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handlePurge}
            disabled={purging}
            variant="contained"
            color="error"
            sx={{ flex: 1 }}
          >
            {purging ? "Lösche…" : "Löschen"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

const formatTime = (mtime: number): string => {
  const d = new Date(mtime * 1000);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
};

const formatSize = (bytes: number): string => {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

function PhotoListRow({ photo, divider }: { photo: Photo; divider: boolean }) {
  return (
    <Box
      component={RouterLink}
      to={`/photo/${encodeURIComponent(photo.event)}/${encodeURIComponent(photo.filename)}`}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: { xs: 1.25, sm: 2 },
        px: { xs: 1.25, sm: 2 },
        py: { xs: 0.75, sm: 1 },
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
          width: { xs: 44, sm: 52 },
          height: { xs: 44, sm: 52 },
          borderRadius: 1,
          overflow: "hidden",
          bgcolor: "grey.100",
          flexShrink: 0,
          position: "relative",
        }}
      >
        <Box
          component="img"
          src={api.thumbUrl(photo)}
          alt={photo.filename}
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
        <Typography
          noWrap
          sx={{
            fontWeight: 500,
            fontSize: { xs: ".85rem", sm: ".9rem" },
            color: "text.primary",
            lineHeight: 1.3,
          }}
        >
          {photo.filename}
        </Typography>
        <Typography
          variant="caption"
          noWrap
          sx={{
            color: "text.secondary",
            display: "block",
            lineHeight: 1.3,
            fontSize: { xs: ".7rem", sm: ".72rem" },
          }}
        >
          {formatTime(photo.mtime)}
        </Typography>
      </Box>

      <Typography
        variant="body2"
        sx={{
          color: "text.secondary",
          fontVariantNumeric: "tabular-nums",
          fontSize: { xs: ".75rem", sm: ".8rem" },
          flexShrink: 0,
          display: { xs: "none", sm: "block" },
        }}
      >
        {formatSize(photo.size)}
      </Typography>
    </Box>
  );
}
