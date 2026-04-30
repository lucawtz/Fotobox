import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Box,
  IconButton,
  Stack,
  Typography,
  Tooltip,
  CircularProgress,
  Snackbar,
  Alert,
} from "@mui/material";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import DownloadRoundedIcon from "@mui/icons-material/DownloadRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import ChevronLeftRoundedIcon from "@mui/icons-material/ChevronLeftRounded";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import { Swiper, SwiperSlide } from "swiper/react";
import { Keyboard, Zoom } from "swiper/modules";
import type { Swiper as SwiperType } from "swiper";
import "swiper/css";
import "swiper/css/zoom";

import { api, Photo } from "../api";
import DeleteDialog from "../components/DeleteDialog";

export default function PhotoView() {
  const { filename } = useParams<{ filename: string }>();
  const navigate = useNavigate();

  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmDel, setConfirmDel] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const swiperRef = useRef<SwiperType | null>(null);

  useEffect(() => {
    api.list().then((r) => {
      setPhotos(r.photos);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const startIndex = useMemo(() => {
    if (!filename) return 0;
    const i = photos.findIndex((p) => p.filename === filename);
    return i < 0 ? 0 : i;
  }, [filename, photos]);

  const current = photos[startIndex];

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  const onSlideChange = (sw: SwiperType) => {
    const p = photos[sw.activeIndex];
    if (p) {
      window.history.replaceState(null, "", `/photo/${encodeURIComponent(p.filename)}`);
    }
  };

  const onDeleted = () => {
    if (!current) return;
    const remaining = photos.filter((p) => p.filename !== current.filename);
    setPhotos(remaining);
    setConfirmDel(false);
    setToast("Foto gelöscht");
    if (remaining.length === 0) {
      navigate("/");
    } else {
      const next = Math.min(startIndex, remaining.length - 1);
      navigate(`/photo/${encodeURIComponent(remaining[next].filename)}`, { replace: true });
    }
  };

  if (loading) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ height: "100dvh" }}>
        <CircularProgress sx={{ color: "primary.light" }} />
      </Stack>
    );
  }

  if (photos.length === 0 || !current) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ height: "100dvh", color: "text.secondary" }}>
        <Typography>Foto nicht gefunden</Typography>
        <IconButton onClick={() => navigate("/")} sx={{ mt: 2 }}>
          <ArrowBackRoundedIcon />
        </IconButton>
      </Stack>
    );
  }

  return (
    <Box
      sx={{
        position: "fixed",
        inset: 0,
        background: "#000",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Top bar */}
      <Box
        sx={{
          position: "absolute",
          top: 0, left: 0, right: 0,
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: { xs: 1.5, sm: 2 },
          py: { xs: 1.25, sm: 1.5 },
          background: "linear-gradient(to bottom, rgba(0,0,0,0.85), transparent)",
          paddingTop: "max(env(safe-area-inset-top), 12px)",
        }}
      >
        <IconButton onClick={() => navigate("/")} sx={{ color: "#fff" }}>
          <ArrowBackRoundedIcon />
        </IconButton>
        <Stack sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{ color: "rgba(255,255,255,0.55)", letterSpacing: ".05em" }}
          >
            {startIndex + 1} / {photos.length}
          </Typography>
          <Typography
            variant="body2"
            noWrap
            sx={{ color: "rgba(255,255,255,0.85)", fontWeight: 500 }}
          >
            {current.filename}
          </Typography>
        </Stack>
        <Tooltip title="Herunterladen">
          <IconButton
            component="a"
            href={api.downloadUrl(current.filename)}
            sx={{ color: "#fff" }}
          >
            <DownloadRoundedIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Löschen">
          <IconButton onClick={() => setConfirmDel(true)} sx={{ color: "#fff" }}>
            <DeleteOutlineRoundedIcon />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Swiper */}
      <Swiper
        modules={[Keyboard, Zoom]}
        keyboard={{ enabled: true }}
        zoom={{ maxRatio: 3 }}
        initialSlide={startIndex}
        onSwiper={(s) => (swiperRef.current = s)}
        onSlideChange={onSlideChange}
        style={{ width: "100%", height: "100%" }}
      >
        {photos.map((p) => (
          <SwiperSlide
            key={p.filename}
            style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <div className="swiper-zoom-container" style={{ width: "100%", height: "100%" }}>
              <img
                src={api.imgUrl(p.filename)}
                alt={p.filename}
                style={{
                  maxWidth: "100%",
                  maxHeight: "100%",
                  objectFit: "contain",
                  userSelect: "none",
                  WebkitUserSelect: "none",
                  pointerEvents: "auto",
                }}
                draggable={false}
              />
            </div>
          </SwiperSlide>
        ))}
      </Swiper>

      {/* Desktop arrows */}
      {photos.length > 1 && (
        <>
          <IconButton
            onClick={() => swiperRef.current?.slidePrev()}
            sx={{
              position: "absolute",
              left: 16, top: "50%",
              transform: "translateY(-50%)",
              bgcolor: "rgba(0,0,0,0.45)",
              color: "#fff",
              display: { xs: "none", md: "inline-flex" },
              "&:hover": { bgcolor: "rgba(0,0,0,0.65)" },
            }}
          >
            <ChevronLeftRoundedIcon fontSize="large" />
          </IconButton>
          <IconButton
            onClick={() => swiperRef.current?.slideNext()}
            sx={{
              position: "absolute",
              right: 16, top: "50%",
              transform: "translateY(-50%)",
              bgcolor: "rgba(0,0,0,0.45)",
              color: "#fff",
              display: { xs: "none", md: "inline-flex" },
              "&:hover": { bgcolor: "rgba(0,0,0,0.65)" },
            }}
          >
            <ChevronRightRoundedIcon fontSize="large" />
          </IconButton>
        </>
      )}

      <DeleteDialog
        open={confirmDel}
        filename={current.filename}
        onClose={() => setConfirmDel(false)}
        onDeleted={onDeleted}
      />

      <Snackbar
        open={!!toast}
        autoHideDuration={2200}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="success" variant="filled" onClose={() => setToast(null)}>
          {toast}
        </Alert>
      </Snackbar>
    </Box>
  );
}
