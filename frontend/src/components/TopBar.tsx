import { ReactNode } from "react";
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
        <Box
          component="img"
          src="/logo-mark.svg"
          alt="Fotobox"
          sx={{
            width: { xs: 32, sm: 36 },
            height: { xs: 32, sm: 36 },
            flexShrink: 0,
            mr: { xs: 1, sm: 1.25 },
            display: "block",
          }}
        />

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
