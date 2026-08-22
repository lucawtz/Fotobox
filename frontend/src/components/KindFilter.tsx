import { Box, ToggleButton, ToggleButtonGroup } from "@mui/material";
import { PhotoFilter } from "../api";

interface Props {
  value: PhotoFilter;
  onChange: (v: PhotoFilter) => void;
  counts: Record<PhotoFilter, number>;
  size?: "small" | "medium";
}

const LABELS: Array<{ key: PhotoFilter; label: string }> = [
  { key: "alle",    label: "Alle" },
  { key: "collage", label: "Collagen" },
  { key: "single",  label: "Einzelbilder" },
];

/** Umschalter zwischen Collagen und Einzelbildern.
 *
 *  Wird vom Aufrufer nur gerendert, wenn das Event ueberhaupt Collagen
 *  enthaelt — auf einer Feier ohne Collage waeren drei Knoepfe, von denen
 *  zwei dasselbe zeigen, nur Rauschen.
 */
export default function KindFilter({ value, onChange, counts, size = "small" }: Props) {
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size={size}
      onChange={(_, next) => { if (next) onChange(next); }}
      aria-label="Bildart"
      sx={{
        flexWrap: "nowrap",
        "& .MuiToggleButton-root": {
          border: "1px solid",
          borderColor: "divider",
          color: "text.secondary",
          px: { xs: 1, sm: 1.5 },
          py: 0.5,
          fontSize: { xs: ".72rem", sm: ".78rem" },
          fontWeight: 500,
          textTransform: "none",
          whiteSpace: "nowrap",
          "&.Mui-selected": {
            bgcolor: "primary.main",
            color: "primary.contrastText",
            "&:hover": { bgcolor: "primary.dark" },
          },
        },
      }}
    >
      {LABELS.map(({ key, label }) => (
        <ToggleButton key={key} value={key} aria-label={label}>
          {label}
          <Box component="span" sx={{ ml: 0.75, opacity: 0.7, fontVariantNumeric: "tabular-nums" }}>
            {counts[key]}
          </Box>
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
