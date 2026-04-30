import { createTheme, alpha } from "@mui/material/styles";

// ── Google-Drive-inspirierte Palette ──────────────────────────────────────────
const driveBlue       = "#1a73e8";
const driveBlueHover  = "#1765cc";
const driveBlueLight  = "#4285f4";
const surface         = "#ffffff";
const surface1        = "#f8f9fa";   // App background
const surface2        = "#f0f4f9";   // Sidebar / hover
const surface3        = "#e8eef7";   // selected nav item
const outline         = "#dadce0";
const outlineSoft     = "#e8eaed";
const onSurface       = "#1f1f1f";
const onSurfaceMuted  = "#444746";
const onSurfaceFaint  = "#5f6368";

const successColor = "#1e8e3e";
const warningColor = "#f29900";
const errorColor   = "#d93025";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main:        driveBlue,
      dark:        driveBlueHover,
      light:       driveBlueLight,
      contrastText: "#ffffff",
    },
    secondary: { main: "#9334e6" },
    success: { main: successColor },
    warning: { main: warningColor },
    error:   { main: errorColor },
    background: { default: surface1, paper: surface },
    text: {
      primary:   onSurface,
      secondary: onSurfaceFaint,
      disabled:  alpha(onSurface, 0.38),
    },
    divider: outlineSoft,
    grey: {
      50:  surface1,
      100: surface2,
      200: surface3,
      300: outlineSoft,
      400: outline,
      500: "#bdc1c6",
      600: onSurfaceFaint,
      700: onSurfaceMuted,
      900: onSurface,
    },
  },
  typography: {
    fontFamily: '"Google Sans", "Inter", system-ui, -apple-system, sans-serif',
    h1: { fontWeight: 500, letterSpacing: "-0.02em" },
    h2: { fontWeight: 500, letterSpacing: "-0.02em" },
    h3: { fontWeight: 500, letterSpacing: "-0.01em" },
    h4: { fontWeight: 500, letterSpacing: "-0.01em" },
    h5: { fontWeight: 500, letterSpacing: "-0.005em" },
    h6: { fontWeight: 500 },
    button: { textTransform: "none", fontWeight: 500, letterSpacing: 0 },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: {
          WebkitTapHighlightColor: "transparent",
          // touch-action: manipulation killt die iOS 300ms-Verzögerung beim
          // Tap und verbietet Double-Tap-Zoom (zoomen geht nur in der
          // PhotoView ueber Pinch).
          touchAction: "manipulation",
          // Safe-Area-Variablen damit Komponenten env() referenzieren können
          // ohne das Plumbing pro File zu wiederholen.
          "--sa-top":    "env(safe-area-inset-top, 0px)",
          "--sa-bottom": "env(safe-area-inset-bottom, 0px)",
          "--sa-left":   "env(safe-area-inset-left, 0px)",
          "--sa-right":  "env(safe-area-inset-right, 0px)",
        },
        body: {
          backgroundColor: surface1,
          minHeight: "100dvh",
          overscrollBehavior: "none",
          color: onSurface,
          overflowX: "hidden",
        },
        // Bessere Scroll-Performance auf langen Listen (iOS)
        "*": { WebkitOverflowScrolling: "touch" },
        "::selection": { background: alpha(driveBlue, 0.22) },
        // Auf XS sollen die Standard-IconButtons komfortabel zu treffen sein.
        "@media (hover: none) and (pointer: coarse)": {
          ".MuiIconButton-root": { padding: "10px" },
        },
      },
    },
    MuiAppBar: {
      defaultProps: { color: "default" },
      styleOverrides: {
        root: {
          backgroundColor: surface,
          backgroundImage: "none",
          color: onSurface,
          borderBottom: `1px solid ${outlineSoft}`,
          boxShadow: "none",
          backdropFilter: "saturate(180%) blur(8px)",
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 999, paddingInline: 20, paddingBlock: 9 },
        contained: { boxShadow: "none", "&:hover": { boxShadow: "none" } },
        outlined: ({ theme }) => ({
          borderColor: theme.palette.divider,
          color: theme.palette.text.primary,
          "&:hover": {
            borderColor: outline,
            backgroundColor: alpha(driveBlue, 0.04),
          },
        }),
        text: {
          "&:hover": { backgroundColor: alpha(driveBlue, 0.06) },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          color: theme.palette.text.secondary,
          transition: "background-color .15s, color .15s",
          "&:hover": { backgroundColor: alpha(onSurface, 0.06) },
        }),
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: 20,
          border: `1px solid ${outlineSoft}`,
          boxShadow:
            "0 1px 2px rgba(60,64,67,.06), 0 8px 24px rgba(60,64,67,.15)",
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          fontSize: 12,
          background: "#3c4043",
          color: "#ffffff",
          fontWeight: 500,
          borderRadius: 6,
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: 10,
          backgroundColor: surface,
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: theme.palette.divider,
          },
          "&:hover .MuiOutlinedInput-notchedOutline": {
            borderColor: outline,
          },
        }),
        // iOS Safari zoomt Inputs <16px automatisch rein. Auf Touch-Devices
        // immer mindestens 16px verwenden, Desktop bleibt 14px.
        input: {
          "@media (hover: none) and (pointer: coarse)": {
            fontSize: 16,
          },
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        outlined: ({ theme }) => ({
          borderColor: theme.palette.divider,
        }),
      },
    },
    MuiChip: {
      styleOverrides: {
        outlined: { borderColor: outline },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          "&:hover": { backgroundColor: alpha(onSurface, 0.06) },
        },
      },
    },
  },
});

export default theme;
