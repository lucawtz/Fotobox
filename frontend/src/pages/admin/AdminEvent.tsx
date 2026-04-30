import { useEffect, useState } from "react";
import {
  Stack,
  TextField,
  Button,
  Slider,
  Box,
  Typography,
  InputAdornment,
  IconButton,
  Snackbar,
  Alert,
  Skeleton,
} from "@mui/material";
import EventRoundedIcon from "@mui/icons-material/EventRounded";
import TimerRoundedIcon from "@mui/icons-material/TimerRounded";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import VisibilityOffRoundedIcon from "@mui/icons-material/VisibilityOffRounded";
import { api, AdminConfig } from "../../api";
import SettingsCard from "./SettingsCard";

export default function AdminEvent() {
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [eventName, setEventName] = useState("");
  const [countdown, setCountdown] = useState(3);
  const [pin, setPin] = useState("");
  const [showPin, setShowPin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    api.admin.config.get().then((c) => {
      setCfg(c);
      setEventName(c.event_name);
      setCountdown(c.countdown_duration);
      setPin(c.admin_pin);
    });
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      await api.admin.config.save({
        event_name: eventName,
        countdown_duration: countdown,
        admin_pin: pin,
      });
      setToast({ severity: "success", msg: "Einstellungen gespeichert" });
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const dirty = !!cfg && (
    eventName !== cfg.event_name ||
    countdown !== cfg.countdown_duration ||
    pin !== cfg.admin_pin
  );

  return (
    <>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            Event
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Anzeigename, Countdown und Admin-Zugang
          </Typography>
        </Box>

        <SettingsCard
          icon={<EventRoundedIcon />}
          title="Event-Name"
          description="Wird im Header der Galerie und auf dem Homescreen angezeigt."
        >
          {cfg ? (
            <TextField
              value={eventName}
              onChange={(e) => setEventName(e.target.value)}
              placeholder="z.B. Lisa & Tom Hochzeit"
              fullWidth
              inputProps={{ maxLength: 60 }}
            />
          ) : (
            <Skeleton variant="rounded" height={56} />
          )}
        </SettingsCard>

        <SettingsCard
          icon={<TimerRoundedIcon />}
          title="Countdown"
          description="Dauer des Foto-Countdowns (1–10 Sekunden)."
        >
          {cfg ? (
            <Box sx={{ px: { xs: 0.5, sm: 1.5 } }}>
              <Stack direction="row" alignItems="center" spacing={3}>
                <Slider
                  value={countdown}
                  onChange={(_, v) => setCountdown(v as number)}
                  min={1} max={10} step={1}
                  marks
                  valueLabelDisplay="auto"
                  sx={{ color: "primary.main" }}
                />
                <Box
                  sx={{
                    minWidth: 64, textAlign: "center",
                    px: 1.5, py: 0.75, borderRadius: 2,
                    bgcolor: "#e8f0fe",
                    color: "primary.main",
                    fontWeight: 600, fontSize: "1.25rem",
                  }}
                >
                  {countdown}s
                </Box>
              </Stack>
            </Box>
          ) : (
            <Skeleton variant="rounded" height={48} />
          )}
        </SettingsCard>

        <SettingsCard
          icon={<LockRoundedIcon />}
          title="Admin-PIN"
          description="Mindestens 4 Zeichen. Wird zum Anmelden und Foto-Löschen verwendet."
        >
          {cfg ? (
            <TextField
              type={showPin ? "text" : "password"}
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              fullWidth
              inputProps={{ maxLength: 24, inputMode: "numeric" }}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPin((s) => !s)} edge="end" size="small">
                      {showPin ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              helperText={pin.length > 0 && pin.length < 4 ? "PIN zu kurz" : " "}
              error={pin.length > 0 && pin.length < 4}
            />
          ) : (
            <Skeleton variant="rounded" height={56} />
          )}
        </SettingsCard>

        <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1.5, pt: 1 }}>
          <Button
            disabled={!dirty || busy}
            onClick={() => {
              if (cfg) {
                setEventName(cfg.event_name);
                setCountdown(cfg.countdown_duration);
                setPin(cfg.admin_pin);
              }
            }}
            color="inherit"
          >
            Verwerfen
          </Button>
          <Button
            disabled={!dirty || busy || pin.length < 4}
            onClick={save}
            variant="contained"
          >
            {busy ? "Speichere…" : "Speichern"}
          </Button>
        </Box>
      </Stack>

      <Snackbar
        open={!!toast}
        autoHideDuration={2400}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity={toast?.severity ?? "info"} variant="filled" onClose={() => setToast(null)}>
          {toast?.msg}
        </Alert>
      </Snackbar>
    </>
  );
}
