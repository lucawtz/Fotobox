import { useEffect, useState } from "react";
import {
  FormControlLabel,
  Stack,
  Switch,
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
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [ssid, setSsid] = useState("");
  const [pwd, setPwd] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  // Kein eigener Config-Wert: "offen" heisst schlicht "kein Passwort
  // gesetzt". Ein zweites Flag koennte dem Passwortfeld widersprechen.
  const [open_, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error" | "info"; msg: string } | null>(null);

  const applyCfg = (c: AdminConfig) => {
    setCfg(c);
    setSsid(c.wifi_ssid ?? "");
    setPwd(c.wifi_password ?? "");
    setOpen(!(c.wifi_password ?? ""));
  };

  useEffect(() => {
    // Ohne .catch() blieb die Seite bei abgelaufener Session stumm auf
    // Skeletons stehen — kein Spinner, kein Fehler.
    api.admin.config.get()
      .then(applyCfg)
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.admin.config.save({ wifi_ssid: ssid, wifi_password: pwd });
      // Gespeicherten Stand uebernehmen. Fehlte das, blieb `dirty` true: die
      // Warnung "WLAN startet neu" blieb stehen, Speichern blieb aktiv — es
      // sah aus, als waere nichts passiert, also drueckt man plausibel ein
      // zweites Mal und startet den Hotspot ein zweites Mal neu.
      setCfg({ ...(cfg as AdminConfig), wifi_ssid: ssid, wifi_password: pwd });
      // Der Server startet den Hotspot mit den neuen Daten neu. Wer das hier
      // gerade bedient, haengt fast immer AN diesem Hotspot — der Abbruch
      // gleich ist erwartet und darf nicht wie ein Fehler aussehen.
      setToast(r.wifi_restarting
        ? { severity: "info",
            msg: "Gespeichert. WLAN startet neu — bitte mit den neuen Daten neu verbinden." }
        : { severity: "success", msg: "WLAN-Einstellungen gespeichert" });
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally { setBusy(false); }
  };

  const dirty = !!cfg && (ssid !== (cfg.wifi_ssid ?? "") || pwd !== (cfg.wifi_password ?? ""));

  return (
    <>
      <Stack spacing={3}>
        {loadErr && (
          <Alert severity="error" variant="outlined">
            Einstellungen konnten nicht geladen werden: {loadErr}
          </Alert>
        )}
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            WLAN
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Zugangsdaten des Fotobox-WLANs — sie stecken im QR-Code auf dem
            Boxbildschirm
          </Typography>
        </Box>

        <SettingsCard
          icon={<WifiRoundedIcon />}
          title="Netzwerk-Name (SSID)"
          description="Steht auf dem Boxbildschirm und steckt im QR-Code. Kurz halten — je länger SSID und Passwort, desto feiner das QR-Muster."
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
          description="8 bis 63 Zeichen (WPA2) — oder ganz weglassen, dann ist das Netz offen."
        >
          {cfg ? (
            <Stack spacing={1.5}>
              <FormControlLabel
                control={
                  <Switch
                    checked={open_}
                    onChange={(e) => {
                      setOpen(e.target.checked);
                      // Leeres Feld IST die Einstellung — der Server liest
                      // "offen" nicht aus einem Flag, sondern daraus, dass
                      // kein Passwort ankommt (gallery_server, hotspot.py).
                      if (e.target.checked) setPwd("");
                    }}
                  />
                }
                label="Offenes WLAN — kein Passwort"
              />
              {open_ ? (
                <Alert severity="warning" variant="outlined">
                  Jeder in Funkreichweite kommt in die Galerie — auch aus der
                  Nachbarwohnung. Dafür entfällt das Abtippen. iPhones zeigen
                  „Ungesichertes Netzwerk“.
                </Alert>
              ) : (
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
              )}
            </Stack>
          ) : <Skeleton variant="rounded" height={56} />}
        </SettingsCard>

        {dirty && (
          <Alert severity="warning" variant="outlined">
            Beim Speichern startet das WLAN neu — alle Geräte fliegen kurz raus,
            auch dieses. Am besten <strong>vor</strong> dem Event ändern.
          </Alert>
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
            color="inherit"
            onClick={() => { if (cfg) applyCfg(cfg); }}
            sx={{ flex: { xs: 1, sm: "0 0 auto" } }}
          >
            Verwerfen
          </Button>
          <Button
            // Leeres Passwort ist gueltig (offenes Netz) — nur 1 bis 7
            // Zeichen sind es nicht, die haelt auch der Server ab.
            disabled={
              !dirty || busy ||
              (pwd.length > 0 && pwd.length < 8) ||
              ssid.trim().length === 0
            }
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
        autoHideDuration={toast?.severity === "info" ? 8000 : 2400}
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
