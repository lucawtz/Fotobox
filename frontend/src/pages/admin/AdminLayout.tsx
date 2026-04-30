import { useState } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import {
  Box,
  AppBar,
  Toolbar,
  Drawer,
  IconButton,
  Typography,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  useMediaQuery,
  useTheme,
  Tooltip,
  Menu,
  MenuItem,
  Avatar,
} from "@mui/material";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import DashboardRoundedIcon from "@mui/icons-material/DashboardRounded";
import EventRoundedIcon from "@mui/icons-material/EventRounded";
import WifiRoundedIcon from "@mui/icons-material/WifiRounded";
import ImageRoundedIcon from "@mui/icons-material/ImageRounded";
import BuildRoundedIcon from "@mui/icons-material/BuildRounded";
import LogoutRoundedIcon from "@mui/icons-material/LogoutRounded";
import PhotoLibraryRoundedIcon from "@mui/icons-material/PhotoLibraryRounded";
import { api } from "../../api";

const NAV_WIDTH = 256;

const NAV_ITEMS = [
  { to: "/admin",             label: "Übersicht", icon: <DashboardRoundedIcon /> },
  { to: "/admin/event",       label: "Event",     icon: <EventRoundedIcon />     },
  { to: "/admin/wifi",        label: "WLAN",      icon: <WifiRoundedIcon />      },
  { to: "/admin/branding",    label: "Logo",      icon: <ImageRoundedIcon />     },
  { to: "/admin/maintenance", label: "Wartung",   icon: <BuildRoundedIcon />     },
];

export default function AdminLayout() {
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up("md"));
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuEl, setMenuEl] = useState<null | HTMLElement>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const sectionTitle =
    NAV_ITEMS.find((i) =>
      i.to === "/admin" ? location.pathname === "/admin" : location.pathname.startsWith(i.to),
    )?.label ?? "Admin";

  const logout = async () => {
    try { await api.admin.logout(); } catch { /* ignore */ }
    navigate("/admin/login", { replace: true });
  };

  const drawerContent = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Box sx={{ p: 2.5, pb: 1.5, display: "flex", alignItems: "center", gap: 1.25 }}>
        <Box
          sx={{
            width: 36, height: 36, borderRadius: "50%",
            display: "grid", placeItems: "center",
            background: "linear-gradient(135deg, rgba(212,168,106,0.22), rgba(212,168,106,0.06))",
            border: "1px solid", borderColor: "divider",
          }}
        >
          <PhotoLibraryRoundedIcon sx={{ color: "primary.light", fontSize: 20 }} />
        </Box>
        <Box>
          <Typography
            variant="subtitle1"
            sx={{ fontFamily: '"Playfair Display", serif', lineHeight: 1.1, color: "primary.light" }}
          >
            Fotobox
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", letterSpacing: ".06em" }}>
            ADMIN
          </Typography>
        </Box>
      </Box>

      <Divider sx={{ mx: 2, my: 1 }} />

      <List sx={{ flex: 1, px: 1.25, py: 0.5 }}>
        {NAV_ITEMS.map((item) => (
          <ListItemButton
            key={item.to}
            component={NavLink}
            to={item.to}
            end={item.to === "/admin"}
            onClick={() => setMobileOpen(false)}
            sx={{
              borderRadius: 999,
              px: 2, py: 1,
              mb: 0.5,
              color: "text.secondary",
              "& .MuiListItemIcon-root": { color: "inherit", minWidth: 38 },
              "&.active": {
                background: "linear-gradient(90deg, rgba(212,168,106,0.18), rgba(212,168,106,0.04))",
                color: "primary.light",
                fontWeight: 600,
              },
              "&:hover": { bgcolor: "rgba(212,168,106,0.06)" },
            }}
          >
            <ListItemIcon>{item.icon}</ListItemIcon>
            <ListItemText
              primaryTypographyProps={{ fontSize: ".925rem", fontWeight: 500 }}
              primary={item.label}
            />
          </ListItemButton>
        ))}
      </List>

      <Divider sx={{ mx: 2 }} />
      <Box sx={{ p: 1.25 }}>
        <ListItemButton
          onClick={() => { setMobileOpen(false); navigate("/"); }}
          sx={{ borderRadius: 999, color: "text.secondary", "&:hover": { bgcolor: "rgba(212,168,106,0.06)" } }}
        >
          <ListItemIcon sx={{ minWidth: 38, color: "inherit" }}>
            <PhotoLibraryRoundedIcon />
          </ListItemIcon>
          <ListItemText primary="Zur Galerie" primaryTypographyProps={{ fontSize: ".9rem" }} />
        </ListItemButton>
        <ListItemButton
          onClick={logout}
          sx={{ borderRadius: 999, color: "error.light", "&:hover": { bgcolor: "rgba(224,83,60,0.08)" } }}
        >
          <ListItemIcon sx={{ minWidth: 38, color: "inherit" }}>
            <LogoutRoundedIcon />
          </ListItemIcon>
          <ListItemText primary="Abmelden" primaryTypographyProps={{ fontSize: ".9rem" }} />
        </ListItemButton>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100dvh" }}>
      {/* Sidebar */}
      {isDesktop ? (
        <Drawer
          variant="permanent"
          PaperProps={{
            sx: {
              width: NAV_WIDTH,
              border: 0,
              borderRight: "1px solid",
              borderColor: "divider",
              background: "rgba(22,16,10,0.6)",
              backdropFilter: "blur(18px)",
            },
          }}
          sx={{ width: NAV_WIDTH, flexShrink: 0 }}
        >
          {drawerContent}
        </Drawer>
      ) : (
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          PaperProps={{ sx: { width: NAV_WIDTH, background: "#16100a" } }}
        >
          {drawerContent}
        </Drawer>
      )}

      {/* Main column */}
      <Box sx={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <AppBar position="sticky" elevation={0}>
          <Toolbar sx={{ minHeight: { xs: 64, sm: 72 }, gap: 1.25, px: { xs: 1.5, sm: 3 } }}>
            {!isDesktop && (
              <IconButton edge="start" onClick={() => setMobileOpen(true)}>
                <MenuRoundedIcon />
              </IconButton>
            )}
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography
                variant="h6"
                sx={{
                  fontFamily: '"Playfair Display", serif',
                  color: "primary.light",
                  fontWeight: 600,
                  lineHeight: 1.1,
                }}
              >
                {sectionTitle}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                Fotobox-Verwaltung
              </Typography>
            </Box>

            <Tooltip title="Konto">
              <IconButton onClick={(e) => setMenuEl(e.currentTarget)}>
                <Avatar
                  sx={{
                    width: 34, height: 34,
                    fontSize: ".9rem",
                    bgcolor: "rgba(212,168,106,0.18)",
                    color: "primary.light",
                    border: "1px solid",
                    borderColor: "divider",
                  }}
                >
                  A
                </Avatar>
              </IconButton>
            </Tooltip>
            <Menu
              anchorEl={menuEl}
              open={Boolean(menuEl)}
              onClose={() => setMenuEl(null)}
              anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
              transformOrigin={{ vertical: "top", horizontal: "right" }}
              slotProps={{ paper: { sx: { mt: 1, minWidth: 180, border: "1px solid", borderColor: "divider" } } }}
            >
              <MenuItem onClick={() => { setMenuEl(null); navigate("/"); }}>
                <ListItemIcon><PhotoLibraryRoundedIcon fontSize="small" /></ListItemIcon>
                Zur Galerie
              </MenuItem>
              <Divider />
              <MenuItem onClick={() => { setMenuEl(null); logout(); }} sx={{ color: "error.light" }}>
                <ListItemIcon><LogoutRoundedIcon fontSize="small" sx={{ color: "error.light" }} /></ListItemIcon>
                Abmelden
              </MenuItem>
            </Menu>
          </Toolbar>
        </AppBar>

        <Box
          component="main"
          sx={{
            flex: 1,
            p: { xs: 2, sm: 3, md: 4 },
            maxWidth: 1100,
            width: "100%",
            mx: "auto",
          }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
