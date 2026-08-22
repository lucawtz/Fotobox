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
  alpha,
} from "@mui/material";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import DashboardRoundedIcon from "@mui/icons-material/DashboardRounded";
import EventRoundedIcon from "@mui/icons-material/EventRounded";
import PrintRoundedIcon from "@mui/icons-material/PrintRounded";
import WifiRoundedIcon from "@mui/icons-material/WifiRounded";
import ImageRoundedIcon from "@mui/icons-material/ImageRounded";
import BuildRoundedIcon from "@mui/icons-material/BuildRounded";
import LogoutRoundedIcon from "@mui/icons-material/LogoutRounded";
import PhotoLibraryRoundedIcon from "@mui/icons-material/PhotoLibraryRounded";
import { api } from "../../api";
import { useAuth } from "./authContext";

const NAV_WIDTH = 256;

interface NavItem {
  to: string;
  label: string;
  icon: JSX.Element;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/admin",             label: "Übersicht", icon: <DashboardRoundedIcon /> },
  { to: "/admin/event",       label: "Event",     icon: <EventRoundedIcon />     },
  { to: "/admin/branding",    label: "Design",    icon: <ImageRoundedIcon />     },
  { to: "/admin/wifi",        label: "WLAN",      icon: <WifiRoundedIcon />     },
  { to: "/admin/print",       label: "Drucken",   icon: <PrintRoundedIcon />,    adminOnly: true },
  { to: "/admin/maintenance", label: "Wartung",   icon: <BuildRoundedIcon />,    adminOnly: true },
];

export default function AdminLayout() {
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up("md"));
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuEl, setMenuEl] = useState<null | HTMLElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { role } = useAuth();
  const isAdmin = role === "admin";

  const navItems = NAV_ITEMS.filter((i) => isAdmin || !i.adminOnly);

  const sectionTitle =
    navItems.find((i) =>
      i.to === "/admin" ? location.pathname === "/admin" : location.pathname.startsWith(i.to),
    )?.label ?? "Admin";

  const logout = async () => {
    try { await api.admin.logout(); } catch { /* ignore */ }
    navigate("/admin/login", { replace: true });
  };

  const drawerContent = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", bgcolor: "grey.50" }}>
      <Box sx={{ p: 2, pt: 2.5, pb: 1.5, display: "flex", alignItems: "center", gap: 1.25 }}>
        <Box
          component="img"
          src="/logo-mark.svg"
          alt="Fotobox"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
          sx={{ width: 36, height: 36, display: "block", flexShrink: 0 }}
        />
        <Box>
          <Typography
            variant="subtitle1"
            sx={{ lineHeight: 1.1, color: "text.primary", fontWeight: 500 }}
          >
            Fotobox
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: ".7rem" }}>
            {isAdmin ? "Admin-Konsole" : "Gastgeber-Bereich"}
          </Typography>
        </Box>
      </Box>

      <List sx={{ flex: 1, px: 1, py: 1 }}>
        {navItems.map((item) => (
          <ListItemButton
            key={item.to}
            component={NavLink}
            to={item.to}
            end={item.to === "/admin"}
            onClick={() => setMobileOpen(false)}
            sx={{
              borderRadius: "0 999px 999px 0",
              pl: 2.5, pr: 2,
              py: 1,
              mb: 0.25,
              ml: -1,
              color: "text.secondary",
              fontWeight: 500,
              "& .MuiListItemIcon-root": { color: "inherit", minWidth: 36 },
              "&.active": {
                bgcolor: alpha(theme.palette.primary.main, 0.12),
                color: "primary.main",
                "& .MuiListItemText-primary": { fontWeight: 600 },
              },
              "&.active:hover": {
                bgcolor: alpha(theme.palette.primary.main, 0.16),
              },
              "&:hover": {
                bgcolor: alpha(theme.palette.text.primary, 0.06),
              },
            }}
          >
            <ListItemIcon>{item.icon}</ListItemIcon>
            <ListItemText
              primaryTypographyProps={{ fontSize: ".9rem", fontWeight: "inherit" }}
              primary={item.label}
            />
          </ListItemButton>
        ))}
      </List>

      <Divider />
      <Box sx={{ p: 1 }}>
        <ListItemButton
          onClick={() => { setMobileOpen(false); navigate("/"); }}
          sx={{ borderRadius: 999, color: "text.secondary" }}
        >
          <ListItemIcon sx={{ minWidth: 36, color: "inherit" }}>
            <PhotoLibraryRoundedIcon />
          </ListItemIcon>
          <ListItemText primary="Zur Galerie" primaryTypographyProps={{ fontSize: ".9rem" }} />
        </ListItemButton>
        <ListItemButton
          onClick={logout}
          sx={{
            borderRadius: 999,
            color: "error.main",
            "&:hover": { bgcolor: alpha(theme.palette.error.main, 0.08) },
          }}
        >
          <ListItemIcon sx={{ minWidth: 36, color: "inherit" }}>
            <LogoutRoundedIcon />
          </ListItemIcon>
          <ListItemText primary="Abmelden" primaryTypographyProps={{ fontSize: ".9rem" }} />
        </ListItemButton>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100dvh", bgcolor: "background.default" }}>
      {isDesktop ? (
        <Drawer
          variant="permanent"
          PaperProps={{
            sx: {
              width: NAV_WIDTH,
              border: 0,
              borderRight: "1px solid",
              borderColor: "divider",
              bgcolor: "grey.50",
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
          PaperProps={{ sx: { width: NAV_WIDTH } }}
        >
          {drawerContent}
        </Drawer>
      )}

      <Box sx={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <AppBar
          position="sticky"
          elevation={0}
          sx={{
            pt: "var(--sa-top)",
            pl: "var(--sa-left)",
            pr: "var(--sa-right)",
          }}
        >
          <Toolbar sx={{ minHeight: { xs: 56, sm: 64 }, gap: { xs: 0.75, sm: 1.25 }, px: { xs: 1, sm: 3 } }}>
            {!isDesktop && (
              <IconButton edge="start" onClick={() => setMobileOpen(true)} aria-label="Menü">
                <MenuRoundedIcon />
              </IconButton>
            )}
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography
                variant="h6"
                noWrap
                sx={{
                  color: "text.primary",
                  fontWeight: 500,
                  lineHeight: 1.15,
                  fontSize: { xs: "1rem", sm: "1.15rem" },
                }}
              >
                {sectionTitle}
              </Typography>
              <Typography
                variant="caption"
                noWrap
                sx={{
                  color: "text.secondary",
                  display: "block",
                  fontSize: { xs: ".7rem", sm: ".75rem" },
                }}
              >
                {isAdmin ? "Fotobox-Verwaltung" : "Eingeschränkter Zugang"}
              </Typography>
            </Box>

            <Tooltip title="Konto">
              <IconButton onClick={(e) => setMenuEl(e.currentTarget)}>
                <Avatar
                  sx={{
                    width: 34, height: 34,
                    fontSize: ".95rem",
                    bgcolor: isAdmin ? "primary.main" : "secondary.main",
                    color: "primary.contrastText",
                    fontWeight: 600,
                  }}
                >
                  {isAdmin ? "A" : "G"}
                </Avatar>
              </IconButton>
            </Tooltip>
            <Menu
              anchorEl={menuEl}
              open={Boolean(menuEl)}
              onClose={() => setMenuEl(null)}
              anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
              transformOrigin={{ vertical: "top", horizontal: "right" }}
              slotProps={{ paper: { sx: { mt: 1, minWidth: 200, border: "1px solid", borderColor: "divider", boxShadow: "0 1px 2px rgba(60,64,67,.1), 0 2px 6px rgba(60,64,67,.15)" } } }}
            >
              <MenuItem onClick={() => { setMenuEl(null); navigate("/"); }}>
                <ListItemIcon><PhotoLibraryRoundedIcon fontSize="small" /></ListItemIcon>
                Zur Galerie
              </MenuItem>
              <Divider />
              <MenuItem onClick={() => { setMenuEl(null); logout(); }} sx={{ color: "error.main" }}>
                <ListItemIcon><LogoutRoundedIcon fontSize="small" sx={{ color: "error.main" }} /></ListItemIcon>
                Abmelden
              </MenuItem>
            </Menu>
          </Toolbar>
        </AppBar>

        <Box
          component="main"
          sx={{
            flex: 1,
            px: { xs: 1.5, sm: 3, md: 4 },
            pt: { xs: 2, sm: 3, md: 4 },
            pb: "calc(var(--sa-bottom) + 24px)",
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
