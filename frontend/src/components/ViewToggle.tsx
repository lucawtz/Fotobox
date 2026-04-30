import { useEffect, useState } from "react";
import { ToggleButton, ToggleButtonGroup, Tooltip } from "@mui/material";
import GridViewRoundedIcon from "@mui/icons-material/GridViewRounded";
import ViewListRoundedIcon from "@mui/icons-material/ViewListRounded";

export type GalleryView = "grid" | "list";

interface Props {
  value: GalleryView;
  onChange: (v: GalleryView) => void;
  size?: "small" | "medium";
}

export default function ViewToggle({ value, onChange, size = "small" }: Props) {
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size={size}
      onChange={(_, next) => { if (next) onChange(next); }}
      sx={{
        "& .MuiToggleButton-root": {
          border: "1px solid",
          borderColor: "divider",
          color: "text.secondary",
          px: 1.25,
          "&.Mui-selected": {
            bgcolor: "primary.main",
            color: "primary.contrastText",
            "&:hover": { bgcolor: "primary.dark" },
          },
        },
      }}
    >
      <Tooltip title="Kachel-Ansicht">
        <ToggleButton value="grid" aria-label="Kachel-Ansicht">
          <GridViewRoundedIcon fontSize="small" />
        </ToggleButton>
      </Tooltip>
      <Tooltip title="Listen-Ansicht">
        <ToggleButton value="list" aria-label="Listen-Ansicht">
          <ViewListRoundedIcon fontSize="small" />
        </ToggleButton>
      </Tooltip>
    </ToggleButtonGroup>
  );
}

const STORAGE_PREFIX = "fotobox.view.";

export function useGalleryView(key: string, initial: GalleryView = "grid"): [GalleryView, (v: GalleryView) => void] {
  const storageKey = STORAGE_PREFIX + key;
  const [view, setView] = useState<GalleryView>(() => {
    try {
      const v = localStorage.getItem(storageKey);
      return v === "list" || v === "grid" ? v : initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try { localStorage.setItem(storageKey, view); } catch { /* ignore */ }
  }, [storageKey, view]);

  return [view, setView];
}
