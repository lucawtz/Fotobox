import { Box } from "@mui/material";
import GridViewRoundedIcon from "@mui/icons-material/GridViewRounded";
import { Link as RouterLink } from "react-router-dom";
import { api, Photo } from "../api";

interface Props { photo: Photo; }

export default function PhotoTile({ photo }: Props) {
  return (
    <Box
      component={RouterLink}
      to={`/photo/${encodeURIComponent(photo.event)}/${encodeURIComponent(photo.filename)}`}
      sx={{
        position: "relative",
        display: "block",
        aspectRatio: "1 / 1",
        overflow: "hidden",
        borderRadius: 1,
        bgcolor: "grey.100",
        textDecoration: "none",
        cursor: "pointer",
        WebkitTapHighlightColor: "transparent",
        // Off-Screen-Tiles komplett aus Layout/Paint nehmen — Pflicht für
        // große Galerien, sonst ruckelt's auf dem Handy beim langen Scrollen.
        contentVisibility: "auto",
        containIntrinsicSize: "auto 200px",
        transition: "box-shadow .2s",
        "@media (hover: hover)": {
          "&:hover": {
            boxShadow: "0 1px 3px rgba(60,64,67,.12), 0 4px 8px rgba(60,64,67,.10)",
          },
          "&:hover img": { transform: "scale(1.04)" },
        },
        "&:active img": { transform: "scale(0.98)" },
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
          display: "block",
          transition: "transform .3s cubic-bezier(.2,.7,.2,1)",
        }}
      />

      {/* Collagen sehen als Thumbnail aus wie jedes andere Bild — im
          Quadrat-Zuschnitt ist das 2x2-Raster kaum zu erkennen. Das Abzeichen
          sagt, dass hinter der Kachel vier Aufnahmen stecken. */}
      {photo.kind === "collage" && (
        <Box
          sx={{
            position: "absolute",
            top: 4,
            right: 4,
            display: "flex",
            alignItems: "center",
            gap: 0.25,
            bgcolor: "rgba(0,0,0,0.55)",
            color: "#fff",
            borderRadius: 0.75,
            px: 0.5,
            py: 0.125,
            fontSize: ".65rem",
            fontWeight: 600,
            lineHeight: 1.6,
            backdropFilter: "blur(4px)",
            pointerEvents: "none",
          }}
        >
          <GridViewRoundedIcon sx={{ fontSize: ".8rem" }} />
          4
        </Box>
      )}
    </Box>
  );
}
