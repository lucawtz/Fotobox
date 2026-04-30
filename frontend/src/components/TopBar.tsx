import { AppBar, Toolbar, Box, IconButton, Typography, Tooltip } from "@mui/material";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";

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
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography
            component="h1"
            variant="h5"
            noWrap
            sx={{
              fontFamily: '"Playfair Display", serif',
              color: "primary.light",
              letterSpacing: "-0.01em",
              fontSize: { xs: "1.15rem", sm: "1.4rem" },
            }}
          >
            {title}
          </Typography>
          {subtitle && (
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", display: "block", lineHeight: 1.2, fontSize: ".72rem" }}
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
              sx={{ color: "text.secondary" }}
            >
              <AdminPanelSettingsRoundedIcon />
            </IconButton>
          </Tooltip>
        )}
      </Toolbar>
    </AppBar>
  );
}
