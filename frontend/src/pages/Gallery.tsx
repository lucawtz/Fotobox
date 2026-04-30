import { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Container,
  Fade,
  Stack,
  Typography,
  CircularProgress,
  Chip,
} from "@mui/material";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import { api, Photo } from "../api";
import TopBar from "../components/TopBar";
import PhotoTile from "../components/PhotoTile";

const POLL_MS = 8000;

export default function Gallery() {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [eventName, setEventName] = useState("Fotobox");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const knownCount = useRef(0);

  const load = useCallback(async () => {
    try {
      const r = await api.list();
      setPhotos(r.photos);
      setEventName(r.event_name);
      knownCount.current = r.count;
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const r = await api.count();
        if (r.count !== knownCount.current) load();
      } catch {
        /* ignore */
      }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  return (
    <>
      <TopBar
        title={eventName}
        subtitle={
          loading
            ? "Lade…"
            : `${photos.length} Foto${photos.length === 1 ? "" : "s"}`
        }
        onRefresh={load}
      />

      <Container maxWidth="xl" disableGutters sx={{ pb: 6 }}>
        {loading && photos.length === 0 && (
          <Stack alignItems="center" sx={{ pt: 12 }}>
            <CircularProgress size={28} sx={{ color: "primary.light" }} />
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
                  bgcolor: "rgba(212,168,106,0.07)",
                  border: "1px solid",
                  borderColor: "divider",
                }}
              >
                <PhotoCameraRoundedIcon sx={{ fontSize: 44, color: "primary.light" }} />
              </Box>
              <Typography variant="h5" sx={{ color: "text.primary" }}>
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
              <PhotoTile key={p.filename} photo={p} />
            ))}
          </Box>
        )}
      </Container>
    </>
  );
}
