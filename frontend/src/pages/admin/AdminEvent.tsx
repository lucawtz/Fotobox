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
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from "@mui/material";
import EventRoundedIcon from "@mui/icons-material/EventRounded";
import SubtitlesRoundedIcon from "@mui/icons-material/SubtitlesRounded";
import TimerRoundedIcon from "@mui/icons-material/TimerRounded";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import VisibilityOffRoundedIcon from "@mui/icons-material/VisibilityOffRounded";
import EventRepeatRoundedIcon from "@mui/icons-material/EventRepeatRounded";
import { api, AdminConfig, EventsResponse } from "../../api";
import SettingsCard from "./SettingsCard";
import { useAuth } from "./authContext";

// Spiegelt config.PIN_MIN_LEN / PIN_MAX_LEN — der Server lehnt alles andere
// mit 400 ab, das hier erspart dem Admin nur den Fehlversuch.
const PIN_MIN = 6;
const PIN_MAX = 12;

export default function AdminEvent() {
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [eventName, setEventName] = useState("");
  const [subtitle,  setSubtitle]  = useState("");
  const [countdown, setCountdown] = useState(3);
  const [adminPin, setAdminPin] = useState("");
  const [hostPin, setHostPin]   = useState("");
  const [showAdminPin, setShowAdminPin] = useState(false);
  const [showHostPin,  setShowHostPin]  = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);
  // Nur fuer die Karte "Neues Event": zeigt, was gerade laeuft.
  const [evs, setEvs] = useState<EventsResponse | null>(null);
  const [evsErr, setEvsErr] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [newBusy, setNewBusy] = useState(false);

  const loadEvents = () =>
    api.events()
      .then((r) => { setEvs(r); setEvsErr(false); })
      // Die Info ist Beiwerk — faellt sie aus, bleibt der Button trotzdem
      // bedienbar. Ueber die Berechtigung entscheidet ohnehin der Server.
      .catch(() => setEvsErr(true));

  useEffect(() => {
    if (isAdmin) loadEvents();
  }, [isAdmin]);

  // Aus der geladenen Config in die Formularfelder. Wird beim Oeffnen, beim
  // Verwerfen UND nach dem Speichern gebraucht.
  const applyCfg = (c: AdminConfig) => {
    setCfg(c);
    setEventName(c.event_name);
    setSubtitle(c.subtitle ?? "");
    setCountdown(c.countdown_duration);
    setAdminPin(c.admin_pin ?? "");
    setHostPin(c.host_pin ?? "");
  };

  useEffect(() => {
    // Ohne .catch() blieb die Seite bei abgelaufener Session oder ueberlastetem
    // Hotspot stumm auf Skeletons stehen — kein Spinner, kein Fehler, nichts.
    api.admin.config.get()
      .then(applyCfg)
      .catch((e) =>
        setLoadErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const payload: Partial<AdminConfig> = {
        event_name: eventName,
        subtitle:   subtitle,
        countdown_duration: countdown,
      };
      if (isAdmin) {
        payload.admin_pin = adminPin;
        payload.host_pin  = hostPin;
      }
      await api.admin.config.save(payload);
      // Gespeicherten Stand als neuen Referenzstand uebernehmen. Fehlte das,
      // blieb `dirty` true: Speichern/Verwerfen blieben aktiv, und ein Klick
      // auf "Verwerfen" holte die Werte von VOR dem Speichern zurueck — sah
      // aus, als waere der Speichervorgang rueckgaengig gemacht worden.
      // Der Server kuerzt event_name/subtitle, deshalb seine Fassung lesen
      // statt der eigenen: sonst zeigt das Feld 45 Zeichen, gespeichert sind 40.
      applyCfg(await api.admin.config.get());
      setToast({ severity: "success", msg: "Einstellungen gespeichert" });
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const startNewEvent = async () => {
    setNewBusy(true);
    try {
      const r = await api.admin.newEvent();
      if (!r.ok) throw new Error(r.error ?? "Event konnte nicht gestartet werden");
      setToast({ severity: "success", msg: `Neues Event: ${r.folder}` });
      setNewOpen(false);
      await loadEvents();
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setNewBusy(false);
    }
  };

  const activeEvent = evs?.events.find((e) => e.active) ?? null;
  // list_events() liefert nur Ordner mit Fotos: kein Treffer heisst, im
  // laufenden Event wurde noch nichts aufgenommen — dann gibt es nichts zu
  // trennen und der Ordnername bliebe derselbe.
  const activeEmpty = !!evs && !activeEvent;

  const dirty = !!cfg && (
    eventName !== cfg.event_name ||
    subtitle  !== (cfg.subtitle ?? "") ||
    countdown !== cfg.countdown_duration ||
    (isAdmin && adminPin !== (cfg.admin_pin ?? "")) ||
    (isAdmin && hostPin  !== (cfg.host_pin  ?? ""))
  );

  // Grenzen kommen vom Server (config.py), damit sie nicht ein zweites Mal
  // verdrahtet sind. Fallback nur fuer die Millisekunde vor dem ersten Laden.
  const nameMax = cfg?.event_name_max ?? 40;
  const subMax  = cfg?.subtitle_max   ?? 60;

  const adminPinValid = !isAdmin || (adminPin.length >= PIN_MIN && adminPin.length <= PIN_MAX);
  const hostPinValid  = !isAdmin || hostPin === ""
    || (hostPin.length >= PIN_MIN && hostPin.length <= PIN_MAX);

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
              // Auf dem Homescreen steht der Name in einer 290 px schmalen
              // Sidebar. Bis hierher schrumpft die Schrift mit; laenger wuerde
              // die Box mitten im Wort umbrechen und mit "…" abschneiden.
              inputProps={{ maxLength: nameMax }}
              helperText={`${eventName.length}/${nameMax} Zeichen — mehr passt nicht auf den Box-Bildschirm`}
              FormHelperTextProps={{
                sx: { color: eventName.length >= nameMax ? "warning.main" : "text.secondary" },
              }}
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
              inputProps={{ maxLength: subMax }}
              helperText={`${subtitle.length}/${subMax} Zeichen — mehr passt nicht auf den Box-Bildschirm`}
              FormHelperTextProps={{
                sx: { color: subtitle.length >= subMax ? "warning.main" : "text.secondary" },
              }}
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
              description={`Voller Zugang. ${PIN_MIN}–${PIN_MAX} Ziffern.`}
            >
              {cfg ? (
                <TextField
                  type={showAdminPin ? "text" : "password"}
                  value={adminPin}
                  onChange={(e) => setAdminPin(e.target.value)}
                  fullWidth
                  inputProps={{ maxLength: PIN_MAX, inputMode: "numeric" }}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={() => setShowAdminPin((s) => !s)} edge="end" size="small">
                          {showAdminPin ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                  helperText={adminPin.length > 0 && adminPin.length < PIN_MIN
                    ? `Mindestens ${PIN_MIN} Ziffern` : " "}
                  error={adminPin.length > 0 && adminPin.length < PIN_MIN}
                />
              ) : (
                <Skeleton variant="rounded" height={56} />
              )}
            </SettingsCard>

            <SettingsCard
              icon={<LockRoundedIcon />}
              title="Gastgeber-PIN"
              description={`Eingeschränkter Zugang: nur Event-Name, Countdown und Logo — und nur das laufende Event, nie das Archiv. ${PIN_MIN}–${PIN_MAX} Ziffern, leer lassen deaktiviert den Gastgeber-Login.`}
            >
              {cfg ? (
                <TextField
                  type={showHostPin ? "text" : "password"}
                  value={hostPin}
                  onChange={(e) => setHostPin(e.target.value)}
                  fullWidth
                  inputProps={{ maxLength: PIN_MAX, inputMode: "numeric" }}
                  placeholder="z.B. 004711"
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={() => setShowHostPin((s) => !s)} edge="end" size="small">
                          {showHostPin ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                  helperText={hostPin.length > 0 && hostPin.length < PIN_MIN
                    ? `Mindestens ${PIN_MIN} Ziffern` : " "}
                  error={hostPin.length > 0 && hostPin.length < PIN_MIN}
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
            onClick={() => { if (cfg) applyCfg(cfg); }}
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

        {isAdmin && (
          <>
            <Divider />

            <SettingsCard
              icon={<EventRepeatRoundedIcon />}
              title="Neues Event starten"
              description="Fotos landen ab sofort in einem frischen Ordner — für Vermietungen über mehrere Tage oder zwei Feiern am selben Tag."
            >
              {evs === null && !evsErr ? (
                <Skeleton variant="rounded" height={92} />
              ) : (
                <Box
                  sx={{
                    p: 2.5,
                    borderRadius: 2.5,
                    bgcolor: "grey.50",
                    border: "1px solid",
                    borderColor: "divider",
                  }}
                >
                  {activeEvent ? (
                    <>
                      <Typography variant="body2" color="text.secondary">
                        Läuft gerade
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.25 }}>
                        {activeEvent.display}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                        {activeEvent.count} Foto{activeEvent.count === 1 ? "" : "s"} in{" "}
                        {activeEvent.folder}
                      </Typography>
                    </>
                  ) : activeEmpty ? (
                    <Typography variant="body2" color="text.secondary">
                      Im laufenden Event liegen noch keine Fotos — es gibt nichts
                      zu trennen.
                    </Typography>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      Laufendes Event nicht abrufbar.
                    </Typography>
                  )}
                </Box>
              )}

              <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
                <Button
                  variant="outlined"
                  startIcon={<EventRepeatRoundedIcon />}
                  disabled={activeEmpty || newBusy}
                  onClick={() => setNewOpen(true)}
                >
                  Neues Event starten
                </Button>
              </Box>
            </SettingsCard>
          </>
        )}
      </Stack>

      <Dialog
        open={newOpen}
        onClose={newBusy ? undefined : () => setNewOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <EventRepeatRoundedIcon color="primary" />
          Neues Event starten?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            {activeEvent
              ? `„${activeEvent.display}" wird abgeschlossen — die ${activeEvent.count} Foto${
                  activeEvent.count === 1 ? "" : "s"
                } bleiben erhalten und sind für dich weiter sichtbar.`
              : "Das laufende Event wird abgeschlossen. Es wird nichts gelöscht."}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            Gäste und Gastgeber sehen ab dann nur noch das neue Event. Der
            Event-Name bleibt unverändert.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button onClick={() => setNewOpen(false)} disabled={newBusy} color="inherit" sx={{ flex: 1 }}>
            Abbrechen
          </Button>
          <Button
            variant="contained"
            disabled={newBusy}
            onClick={startNewEvent}
            sx={{ flex: 1 }}
          >
            {newBusy ? "Starte…" : "Starten"}
          </Button>
        </DialogActions>
      </Dialog>

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
