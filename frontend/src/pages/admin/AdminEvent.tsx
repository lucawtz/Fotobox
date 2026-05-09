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
import SubtitlesRoundedIcon from "@mui/icons-material/SubtitlesRounded";
import TimerRoundedIcon from "@mui/icons-material/TimerRounded";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import InstagramIcon from "@mui/icons-material/Instagram";
import EventAvailableRoundedIcon from "@mui/icons-material/EventAvailableRounded";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import VisibilityOffRoundedIcon from "@mui/icons-material/VisibilityOffRounded";
import { api, AdminConfig } from "../../api";
import SettingsCard from "./SettingsCard";
import { useAuth } from "./authContext";

export default function AdminEvent() {
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [eventName, setEventName] = useState("");
  const [subtitle,  setSubtitle]  = useState("");
  const [instagramUrl, setInstagramUrl] = useState("");
  const [bookingUrl,   setBookingUrl]   = useState("");
  const [countdown, setCountdown] = useState(3);
  const [adminPin, setAdminPin] = useState("");
  const [hostPin, setHostPin]   = useState("");
  const [showAdminPin, setShowAdminPin] = useState(false);
  const [showHostPin,  setShowHostPin]  = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    api.admin.config.get().then((c) => {
      setCfg(c);
      setEventName(c.event_name);
      setSubtitle(c.subtitle ?? "");
      setInstagramUrl(c.instagram_url ?? "");
      setBookingUrl(c.booking_url ?? "");
      setCountdown(c.countdown_duration);
      setAdminPin(c.admin_pin ?? "");
      setHostPin(c.host_pin ?? "");
    });
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const payload: Partial<AdminConfig> = {
        event_name: eventName,
        subtitle:   subtitle,
        instagram_url: instagramUrl,
        booking_url:   bookingUrl,
        countdown_duration: countdown,
      };
      if (isAdmin) {
        payload.admin_pin = adminPin;
        payload.host_pin  = hostPin;
      }
      await api.admin.config.save(payload);
      setToast({ severity: "success", msg: "Einstellungen gespeichert" });
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const dirty = !!cfg && (
    eventName !== cfg.event_name ||
    subtitle  !== (cfg.subtitle ?? "") ||
    instagramUrl !== (cfg.instagram_url ?? "") ||
    bookingUrl   !== (cfg.booking_url   ?? "") ||
    countdown !== cfg.countdown_duration ||
    (isAdmin && adminPin !== (cfg.admin_pin ?? "")) ||
    (isAdmin && hostPin  !== (cfg.host_pin  ?? ""))
  );

  const adminPinValid = !isAdmin || (adminPin.length >= 4 && adminPin.length <= 12);
  const hostPinValid  = !isAdmin || hostPin === "" || (hostPin.length >= 4 && hostPin.length <= 12);

  return (
    <>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            Event
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isAdmin ? "Anzeigename, Countdown und PIN-Zugänge" : "Anzeigename und Countdown"}
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
          icon={<SubtitlesRoundedIcon />}
          title="Untertitel"
          description="Erscheint klein unter dem Event-Namen — z.B. das Datum oder ein Spruch."
        >
          {cfg ? (
            <TextField
              value={subtitle}
              onChange={(e) => setSubtitle(e.target.value)}
              placeholder="z.B. 30. April 2026"
              fullWidth
              inputProps={{ maxLength: 80 }}
            />
          ) : (
            <Skeleton variant="rounded" height={56} />
          )}
        </SettingsCard>

        <SettingsCard
          icon={<InstagramIcon />}
          title="Instagram"
          description="Wird unter dem QR-Code in der Sidebar als '@handle' angezeigt. Leer lassen, um die Zeile auszublenden."
        >
          {cfg ? (
            <TextField
              value={instagramUrl}
              onChange={(e) => setInstagramUrl(e.target.value)}
              placeholder="https://instagram.com/dein_handle"
              fullWidth
              inputProps={{ maxLength: 200 }}
            />
          ) : (
            <Skeleton variant="rounded" height={56} />
          )}
        </SettingsCard>

        <SettingsCard
          icon={<EventAvailableRoundedIcon />}
          title="Termine buchen"
          description="Link zur Buchungs-Webseite. Erscheint unter dem QR-Code als 'Termine buchen'-Zeile."
        >
          {cfg ? (
            <TextField
              value={bookingUrl}
              onChange={(e) => setBookingUrl(e.target.value)}
              placeholder="https://deine-fotobox.de/termine"
              fullWidth
              inputProps={{ maxLength: 200 }}
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

        {isAdmin && (
          <>
            <SettingsCard
              icon={<LockRoundedIcon />}
              title="Admin-PIN"
              description="Voller Zugang. 4–12 Zeichen."
            >
              {cfg ? (
                <TextField
                  type={showAdminPin ? "text" : "password"}
                  value={adminPin}
                  onChange={(e) => setAdminPin(e.target.value)}
                  fullWidth
                  inputProps={{ maxLength: 12, inputMode: "numeric" }}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={() => setShowAdminPin((s) => !s)} edge="end" size="small">
                          {showAdminPin ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                  helperText={adminPin.length > 0 && adminPin.length < 4 ? "PIN zu kurz" : " "}
                  error={adminPin.length > 0 && adminPin.length < 4}
                />
              ) : (
                <Skeleton variant="rounded" height={56} />
              )}
            </SettingsCard>

            <SettingsCard
              icon={<LockRoundedIcon />}
              title="Gastgeber-PIN"
              description="Eingeschränkter Zugang: nur Event-Name, Countdown und Logo. Leer lassen, um Gastgeber-Login zu deaktivieren."
            >
              {cfg ? (
                <TextField
                  type={showHostPin ? "text" : "password"}
                  value={hostPin}
                  onChange={(e) => setHostPin(e.target.value)}
                  fullWidth
                  inputProps={{ maxLength: 12, inputMode: "numeric" }}
                  placeholder="z.B. 0000"
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={() => setShowHostPin((s) => !s)} edge="end" size="small">
                          {showHostPin ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                  helperText={hostPin.length > 0 && hostPin.length < 4 ? "PIN zu kurz" : " "}
                  error={hostPin.length > 0 && hostPin.length < 4}
                />
              ) : (
                <Skeleton variant="rounded" height={56} />
              )}
            </SettingsCard>
          </>
        )}

        <Box
          sx={{
            display: "flex",
            justifyContent: { xs: "stretch", sm: "flex-end" },
            gap: 1.5,
            pt: 1,
          }}
        >
          <Button
            disabled={!dirty || busy}
            onClick={() => {
              if (cfg) {
                setEventName(cfg.event_name);
                setSubtitle(cfg.subtitle ?? "");
                setInstagramUrl(cfg.instagram_url ?? "");
                setBookingUrl(cfg.booking_url ?? "");
                setCountdown(cfg.countdown_duration);
                setAdminPin(cfg.admin_pin ?? "");
                setHostPin(cfg.host_pin ?? "");
              }
            }}
            color="inherit"
            sx={{ flex: { xs: 1, sm: "0 0 auto" } }}
          >
            Verwerfen
          </Button>
          <Button
            disabled={!dirty || busy || !adminPinValid || !hostPinValid}
            onClick={save}
            variant="contained"
            sx={{ flex: { xs: 1, sm: "0 0 auto" } }}
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
