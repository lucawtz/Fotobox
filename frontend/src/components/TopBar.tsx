import { AppBar, Toolbar, Box, IconButton, Typography, Tooltip } from "@mui/material";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import PhotoLibraryRoundedIcon from "@mui/icons-material/PhotoLibraryRounded";

interface Props {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
  showAdmin?: boolean;
}

export default function TopBar({ title, subtitle, onRefresh, showAdmin = true }: Props) {
  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ minHeight: { xs: 64, sm: 72 }, gap: 1, px: { xs: 2, sm: 3 } }}>
        <Box
          sx={{
            width: 36, height: 36, borderRadius: "50%",
            display: "grid", placeItems: "center", flexShrink: 0,
            bgcolor: "primary.main",
            color: "primary.contrastText",
            mr: 1.25,
          }}
        >
          <PhotoLibraryRoundedIcon sx={{ fontSize: 20 }} />
        </Box>

        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography
            component="h1"
            variant="h6"
            noWrap
            sx={{
              color: "text.primary",
              letterSpacing: "-0.01em",
              fontSize: { xs: "1.05rem", sm: "1.2rem" },
              fontWeight: 500,
              lineHeight: 1.2,
            }}
          >
            {title}
          </Typography>
          {subtitle && (
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", display: "block", lineHeight: 1.2, fontSize: ".75rem" }}
            >
              {subtitle}
            </Typography>
          )}
        </Box>

        {onRefresh && (
          <Tooltip title="Aktualisieren">
            <IconButton onClick={onRefresh} size="medium">
              <RefreshRoundedIcon />
            </IconButton>
          </Tooltip>
        )}

        {showAdmin && (
          <Tooltip title="Admin">
            <IconButton
              onClick={() => { window.location.href = "/admin"; }}
              size="medium"
            >
              <AdminPanelSettingsRoundedIcon />
            </IconButton>
          </Tooltip>
        )}
      </Toolbar>
    </AppBar>
  );
}
