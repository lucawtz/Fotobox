import { useEffect, useRef, useState } from "react";
import { Box, Skeleton } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { api, Photo } from "../api";

interface Props { photo: Photo; }

export default function PhotoTile({ photo }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setSrc(api.thumbUrl(photo.filename));
            io.disconnect();
            break;
          }
        }
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [photo.filename]);

  return (
    <Box
      ref={ref}
      component={RouterLink}
      to={`/photo/${encodeURIComponent(photo.filename)}`}
      sx={{
        position: "relative",
        display: "block",
        aspectRatio: "1 / 1",
        overflow: "hidden",
        borderRadius: 2,
        bgcolor: "background.paper",
        textDecoration: "none",
        cursor: "pointer",
        transition: "transform .25s cubic-bezier(.2,.7,.2,1), box-shadow .25s",
        WebkitTapHighlightColor: "transparent",
        "&:hover": {
          transform: { sm: "translateY(-2px)" },
          boxShadow: { sm: "0 12px 30px rgba(0,0,0,0.45)" },
        },
        "&:hover img": { transform: { sm: "scale(1.06)" } },
        "&:active img": { transform: "scale(0.98)" },
      }}
    >
      {!loaded && (
        <Skeleton
          variant="rectangular"
          animation="wave"
          sx={{ position: "absolute", inset: 0, bgcolor: "rgba(212,168,106,0.06)" }}
        />
      )}
      {src && (
        <Box
          component="img"
          src={src}
          alt={photo.filename}
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          sx={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            opacity: loaded ? 1 : 0,
            transition: "opacity .35s ease, transform .4s cubic-bezier(.2,.7,.2,1)",
            display: "block",
          }}
        />
      )}
    </Box>
  );
}
