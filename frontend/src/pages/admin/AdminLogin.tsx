import { useState, FormEvent } from "react";
import { useNavigate, useLocation, Link as RouterLink } from "react-router-dom";
import {
  Box,
  Stack,
  Paper,
  Typography,
  TextField,
  Button,
  Alert,
  Link,
  CircularProgress,
} from "@mui/material";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import { api } from "../../api";

export default function AdminLogin() {
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/admin";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!pin) return;
    setBusy(true); setError(null);
    try {
      const r = await api.admin.login(pin);
      if (r.ok) navigate(from, { replace: true });
      else setError(r.error ?? "Falscher PIN");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        px: { xs: 2, sm: 3 },
        py: 3,
        pt: "calc(var(--sa-top) + 24px)",
        pb: "calc(var(--sa-bottom) + 24px)",
      }}
    >
      <Paper
        elevation={0}
        sx={{
          width: "100%",
          maxWidth: 420,
          p: { xs: 3, sm: 4.5 },
          borderRadius: 4,
          border: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
          boxShadow: "0 1px 2px rgba(60,64,67,.06), 0 8px 24px rgba(60,64,67,.10)",
        }}
      >
        <Stack spacing={2.5} alignItems="center" sx={{ textAlign: "center", mb: 3 }}>
          <Box
            sx={{
              width: 64, height: 64, borderRadius: "50%",
              display: "grid", placeItems: "center",
              bgcolor: "primary.main",
              color: "primary.contrastText",
            }}
          >
            <LockRoundedIcon />
          </Box>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 500 }}>
              Konfiguration
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Gib deinen PIN ein – Admin oder Gastgeber
            </Typography>
          </Box>
        </Stack>

        <form onSubmit={submit}>
          <Stack spacing={2}>
            {error && <Alert severity="error" variant="outlined">{error}</Alert>}
            <TextField
              autoFocus
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="••••"
              fullWidth
              disabled={busy}
              inputProps={{
                style: { textAlign: "center", letterSpacing: "0.4em", fontSize: "1.25rem" },
                maxLength: 12,
              }}
            />
            <Button
              type="submit"
              variant="contained"
              disabled={busy || pin.length === 0}
              size="large"
              fullWidth
              startIcon={busy ? <CircularProgress size={18} color="inherit" /> : undefined}
            >
              {busy ? "Prüfe…" : "Anmelden"}
            </Button>
            <Link
              component={RouterLink}
              to="/"
              sx={{ textAlign: "center", color: "text.secondary", fontSize: ".85rem", textDecoration: "none" }}
            >
              ← Zurück zur Galerie
            </Link>
          </Stack>
        </form>
      </Paper>
    </Box>
  );
}
