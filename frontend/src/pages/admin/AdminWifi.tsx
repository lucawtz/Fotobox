import { useEffect, useState } from "react";
import {
  Stack,
  TextField,
  Button,
  Box,
  Typography,
  InputAdornment,
  IconButton,
  Snackbar,
  Alert,
  Skeleton,
} from "@mui/material";
import WifiRoundedIcon from "@mui/icons-material/WifiRounded";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import VisibilityOffRoundedIcon from "@mui/icons-material/VisibilityOffRounded";
import { api, AdminConfig } from "../../api";
import SettingsCard from "./SettingsCard";

export default function AdminWifi() {
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [ssid, setSsid] = useState("");
  const [pwd, setPwd] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    api.admin.config.get().then((c) => {
      setCfg(c);
      setSsid(c.wifi_ssid);
      setPwd(c.wifi_password);
    });
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      await api.admin.config.save({ wifi_ssid: ssid, wifi_password: pwd });
      setToast({ severity: "success", msg: "WLAN-Einstellungen gespeichert" });
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally { setBusy(false); }
  };

  const dirty = !!cfg && (ssid !== cfg.wifi_ssid || pwd !== cfg.wifi_password);

  return (
    <>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            WLAN
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Hotspot-Daten, die auf der Galerie als QR-Code angezeigt werden können
          </Typography>
        </Box>

        <SettingsCard
          icon={<WifiRoundedIcon />}
          title="Netzwerk-Name (SSID)"
          description="Wird Gästen für die Verbindung zum Fotobox-WLAN angezeigt."
        >
          {cfg ? (
            <TextField
              value={ssid}
              onChange={(e) => setSsid(e.target.value)}
              placeholder="Fotobox"
              fullWidth
              inputProps={{ maxLength: 32 }}
            />
          ) : <Skeleton variant="rounded" height={56} />}
        </SettingsCard>

        <SettingsCard
          icon={<LockRoundedIcon />}
          title="WLAN-Passwort"
          description="Mindestens 8 Zeichen für WPA2."
        >
          {cfg ? (
            <TextField
              type={showPwd ? "text" : "password"}
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
              fullWidth
              inputProps={{ maxLength: 63 }}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPwd((s) => !s)} edge="end" size="small">
                      {showPwd ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              helperText={pwd.length > 0 && pwd.length < 8 ? "Passwort zu kurz" : " "}
              error={pwd.length > 0 && pwd.length < 8}
            />
          ) : <Skeleton variant="rounded" height={56} />}
        </SettingsCard>

        <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1.5, pt: 1 }}>
          <Button
            disabled={!dirty || busy}
            color="inherit"
            onClick={() => {
              if (cfg) { setSsid(cfg.wifi_ssid); setPwd(cfg.wifi_password); }
            }}
          >
            Verwerfen
          </Button>
          <Button
            disabled={!dirty || busy || (pwd.length > 0 && pwd.length < 8)}
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
