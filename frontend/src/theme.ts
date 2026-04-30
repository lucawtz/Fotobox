import { createTheme, alpha } from "@mui/material/styles";

const accent = "#d4a86a";
const accentBright = "#f0c98a";
const bgDeep = "#0a0604";
const bgPaper = "#16100a";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary:   { main: accent, light: accentBright, contrastText: "#1a0a02" },
    secondary: { main: "#e07a4a" },
    error:     { main: "#e0533c" },
    background: { default: bgDeep, paper: bgPaper },
    text: {
      primary:   "#f3e9d2",
      secondary: alpha("#f3e9d2", 0.62),
      disabled:  alpha("#f3e9d2", 0.32),
    },
    divider: alpha(accent, 0.12),
  },
  typography: {
    fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
    h1: { fontFamily: '"Playfair Display", serif', fontWeight: 700, letterSpacing: "-0.02em" },
    h2: { fontFamily: '"Playfair Display", serif', fontWeight: 700, letterSpacing: "-0.02em" },
    h3: { fontFamily: '"Playfair Display", serif', fontWeight: 600 },
    h5: { fontWeight: 600, letterSpacing: "-0.01em" },
    h6: { fontWeight: 600, letterSpacing: "-0.01em" },
    button: { textTransform: "none", fontWeight: 600, letterSpacing: 0 },
  },
  shape: { borderRadius: 14 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: { WebkitTapHighlightColor: "transparent" },
        body: {
          background: `radial-gradient(circle at 20% -10%, ${alpha(accent, 0.10)} 0%, transparent 55%), ${bgDeep}`,
          backgroundAttachment: "fixed",
          minHeight: "100dvh",
          overscrollBehavior: "none",
        },
        "::selection": { background: alpha(accent, 0.35) },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: ({ theme }) => ({
          backgroundColor: alpha(bgPaper, 0.7),
          backgroundImage: "none",
          backdropFilter: "blur(18px) saturate(160%)",
          WebkitBackdropFilter: "blur(18px) saturate(160%)",
          borderBottom: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 999, paddingInline: 20, paddingBlock: 10 },
        contained: { boxShadow: "none", "&:hover": { boxShadow: "none" } },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          color: theme.palette.text.primary,
          transition: "background-color .15s, color .15s",
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
        paper: ({ theme }) => ({
          background: bgPaper,
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: 20,
        }),
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { fontSize: 12, background: "#231507", color: "#f3e9d2" },
      },
    },
  },
});

export default theme;
