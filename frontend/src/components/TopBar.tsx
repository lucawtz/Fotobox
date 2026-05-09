import { ReactNode, useState } from "react";
import { AppBar, Toolbar, Box, IconButton, Typography, Tooltip } from "@mui/material";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";

interface Props {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
  showAdmin?: boolean;
  actions?: ReactNode;
}

/**
 * Markenlogo mit Fallback-Kette:
 *   1. /api/admin/logo/preview — vom Mieter hochgeladenes Logo (immer aktuell)
 *   2. /logo-mark.svg — Fallback-Asset aus frontend/public
 *   3. ausblenden, falls beides fehlt → kein Browser-Fragezeichen
 */
function BrandLogo({ size }: { size: { xs: number; sm: number } }) {
  // Stage 0 = Custom-Logo, Stage 1 = static SVG, hidden = nichts mehr probieren.
  const [stage, setStage] = useState<0 | 1>(0);
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;

  const src = stage === 0 ? "/api/admin/logo/preview" : "/logo-mark.svg";
  return (
    <Box
      component="img"
      src={src}
      alt="Logo"
      onError={() => (stage === 0 ? setStage(1) : setHidden(true))}
      sx={{
        width: size,
        height: size,
        flexShrink: 0,
        mr: { xs: 1, sm: 1.25 },
        display: "block",
        objectFit: "cover",
        // Rund maskieren — passt zum Look der Box-Sidebar und macht
        // rechteckige Mieter-Logos sauber kreisförmig.
        borderRadius: "50%",
        bgcolor: "#fff",
      }}
    />
  );
}

export default function TopBar({ title, subtitle, onRefresh, showAdmin = true, actions }: Props) {
  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        // Notch / Status-Bar nicht überdecken (iOS, Android-Edge)
        pt: "var(--sa-top)",
        // Auf Mobile etwas weniger Padding-X — Logo und Buttons sollen
        // nicht den ganzen Header verschlucken.
        px: "var(--sa-left)",
      }}
    >
      <Toolbar
        sx={{
          minHeight: { xs: 56, sm: 72 },
          gap: { xs: 0.5, sm: 1 },
          px: { xs: 1.5, sm: 3 },
        }}
      >
        <BrandLogo size={{ xs: 32, sm: 36 }} />

        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography
            component="h1"
            variant="h6"
            noWrap
            sx={{
              color: "text.primary",
              letterSpacing: "-0.01em",
              fontSize: { xs: "1rem", sm: "1.2rem" },
              fontWeight: 500,
              lineHeight: 1.2,
            }}
          >
            {title}
          </Typography>
          {subtitle && (
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
          )}
        </Box>

        {actions}

        {onRefresh && (
          <Tooltip title="Aktualisieren">
            <IconButton onClick={onRefresh} size="medium" aria-label="Aktualisieren">
              <RefreshRoundedIcon />
            </IconButton>
          </Tooltip>
        )}

        {showAdmin && (
          <Tooltip title="Admin">
            <IconButton
              onClick={() => { window.location.href = "/admin"; }}
              size="medium"
              aria-label="Admin"
            >
              <AdminPanelSettingsRoundedIcon />
            </IconButton>
          </Tooltip>
        )}
      </Toolbar>
    </AppBar>
  );
}
