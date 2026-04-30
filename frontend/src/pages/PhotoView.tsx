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

import { api, Photo, photoKey } from "../api";
import DeleteDialog from "../components/DeleteDialog";

export default function PhotoView() {
  const { event, filename } = useParams<{ event: string; filename: string }>();
  const navigate = useNavigate();

  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmDel, setConfirmDel] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const swiperRef = useRef<SwiperType | null>(null);

  useEffect(() => {
    api.list(event ?? null).then((r) => {
      setPhotos(r.photos);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [event]);

  const startIndex = useMemo(() => {
    if (!filename || !event) return 0;
    const i = photos.findIndex((p) => p.event === event && p.filename === filename);
    return i < 0 ? 0 : i;
  }, [event, filename, photos]);

  const current = photos[startIndex];

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  const onSlideChange = (sw: SwiperType) => {
    const p = photos[sw.activeIndex];
    if (p) {
      window.history.replaceState(
        null, "",
        `/photo/${encodeURIComponent(p.event)}/${encodeURIComponent(p.filename)}`,
      );
    }
  };

  const backTo = event ? `/event/${encodeURIComponent(event)}` : "/";

  const onDeleted = () => {
    if (!current) return;
    const remaining = photos.filter((p) => photoKey(p) !== photoKey(current));
    setPhotos(remaining);
    setConfirmDel(false);
    setToast("Foto gelöscht");
    if (remaining.length === 0) {
      navigate(backTo);
    } else {
      const next = Math.min(startIndex, remaining.length - 1);
      const np = remaining[next];
      navigate(
        `/photo/${encodeURIComponent(np.event)}/${encodeURIComponent(np.filename)}`,
        { replace: true },
      );
    }
  };

  if (loading) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ height: "100dvh" }}>
        <CircularProgress />
      </Stack>
    );
  }

  if (photos.length === 0 || !current) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ height: "100dvh", color: "text.secondary" }}>
        <Typography>Foto nicht gefunden</Typography>
        <IconButton onClick={() => navigate(backTo)} sx={{ mt: 2 }}>
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
      {/* Top-Bar: Back + Counter — Aktionen wandern auf Mobile in die Bottom-Bar */}
      <Box
        sx={{
          position: "absolute",
          top: 0, left: 0, right: 0,
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: { xs: 1, sm: 2 },
          pt: "max(var(--sa-top), 8px)",
          pb: { xs: 1, sm: 1.5 },
          pl: "max(var(--sa-left), 12px)",
          pr: "max(var(--sa-right), 12px)",
          background: "linear-gradient(to bottom, rgba(0,0,0,0.85), transparent)",
        }}
      >
        <IconButton onClick={() => navigate(backTo)} sx={{ color: "#fff" }} aria-label="Zurück">
          <ArrowBackRoundedIcon />
        </IconButton>
        <Stack sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{
              color: "rgba(255,255,255,0.55)",
              letterSpacing: ".05em",
              fontSize: { xs: ".7rem", sm: ".75rem" },
            }}
          >
            {startIndex + 1} / {photos.length} · {current.event}
          </Typography>
          <Typography
            variant="body2"
            noWrap
            sx={{
              color: "rgba(255,255,255,0.85)",
              fontWeight: 500,
              fontSize: { xs: ".85rem", sm: ".9rem" },
            }}
          >
            {current.filename}
          </Typography>
        </Stack>
        {/* Auf Desktop: Aktionen oben rechts. Auf Mobile: in der Bottom-Bar. */}
        <Tooltip title="Herunterladen">
          <IconButton
            component="a"
            href={api.downloadUrl(current)}
            sx={{ color: "#fff", display: { xs: "none", sm: "inline-flex" } }}
            aria-label="Herunterladen"
          >
            <DownloadRoundedIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Löschen">
          <IconButton
            onClick={() => setConfirmDel(true)}
            sx={{ color: "#fff", display: { xs: "none", sm: "inline-flex" } }}
            aria-label="Löschen"
          >
            <DeleteOutlineRoundedIcon />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Bottom-Action-Bar nur auf Mobile — wie Google Photos */}
      <Box
        sx={{
          display: { xs: "flex", sm: "none" },
          position: "absolute",
          bottom: 0, left: 0, right: 0,
          zIndex: 10,
          alignItems: "center",
          justifyContent: "space-around",
          gap: 1,
          px: 1,
          pt: 1.5,
          pb: "max(var(--sa-bottom), 12px)",
          pl: "max(var(--sa-left), 8px)",
          pr: "max(var(--sa-right), 8px)",
          background: "linear-gradient(to top, rgba(0,0,0,0.85), transparent)",
        }}
      >
        <BottomAction
          icon={<DownloadRoundedIcon />}
          label="Speichern"
          component="a"
          href={api.downloadUrl(current)}
        />
        <BottomAction
          icon={<DeleteOutlineRoundedIcon />}
          label="Löschen"
          onClick={() => setConfirmDel(true)}
          danger
        />
      </Box>

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
            key={photoKey(p)}
            style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <div className="swiper-zoom-container" style={{ width: "100%", height: "100%" }}>
              <img
                src={api.previewUrl(p)}
                alt={p.filename}
                style={{
                  maxWidth: "100%",
                  maxHeight: "100%",
                  objectFit: "contain",
                  userSelect: "none",
                  WebkitUserSelect: "none",
                }}
                draggable={false}
              />
            </div>
          </SwiperSlide>
        ))}
      </Swiper>

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
        photo={current}
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

interface BottomActionProps {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  href?: string;
  component?: "button" | "a";
  danger?: boolean;
}

function BottomAction({ icon, label, onClick, href, component = "button", danger }: BottomActionProps) {
  const color = danger ? "#ff8a80" : "#fff";
  return (
    <Box
      component={component}
      href={href}
      onClick={onClick}
      sx={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 0.4,
        py: 1.25,
        px: 1,
        background: "transparent",
        border: 0,
        cursor: "pointer",
        textDecoration: "none",
        color,
        borderRadius: 2,
        minHeight: 56,
        "&:active": { bgcolor: "rgba(255,255,255,0.08)" },
      }}
    >
      <Box sx={{ display: "grid", placeItems: "center", "& > svg": { fontSize: 24 } }}>
        {icon}
      </Box>
      <Typography sx={{ fontSize: ".72rem", fontWeight: 500, color }}>
        {label}
      </Typography>
    </Box>
  );
}
