import { useEffect, useState } from "react";
import {
  Box,
  Paper,
  Typography,
  LinearProgress,
  Stack,
  Chip,
  Button,
  Skeleton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Snackbar,
  Alert,
  CircularProgress,
} from "@mui/material";
import PhotoLibraryRoundedIcon from "@mui/icons-material/PhotoLibraryRounded";
import StorageRoundedIcon from "@mui/icons-material/StorageRounded";
import CameraAltRoundedIcon from "@mui/icons-material/CameraAltRounded";
import CelebrationRoundedIcon from "@mui/icons-material/CelebrationRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";
import RestartAltRoundedIcon from "@mui/icons-material/RestartAltRounded";
import { api, AdminStatus } from "../../api";
import { useAuth } from "./authContext";

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  accent?: "primary" | "success" | "warning" | "error";
  loading?: boolean;
  /** Freitext statt Kennzahl: darf auf zwei Zeilen umbrechen und kleiner
   *  werden. Eine Ellipse waere hier nutzlos — von einem 40 Zeichen langen
   *  Event-Namen bliebe in einer Viertelspalte nur der Anfang stehen. */
  wrapValue?: boolean;
}

function StatCard({ icon, label, value, hint, accent = "primary", loading,
                    wrapValue }: StatCardProps) {
  const accentBg =
    accent === "success" ? "#e6f4ea" :
    accent === "warning" ? "#fef7e0" :
    accent === "error"   ? "#fce8e6" :
                           "#e8f0fe";
  const iconColor =
    accent === "success" ? "#1e8e3e" :
    accent === "warning" ? "#b06000" :
    accent === "error"   ? "#c5221f" :
                           "#1a73e8";

  return (
    <Paper
      elevation={0}
      sx={{
        p: { xs: 1.5, sm: 2.5 },
        borderRadius: { xs: 2.5, sm: 3 },
        border: "1px solid",
        borderColor: "divider",
        height: "100%",
        transition: "box-shadow .15s",
        "&:hover": {
          boxShadow: "0 1px 2px rgba(60,64,67,.10), 0 2px 6px rgba(60,64,67,.08)",
        },
      }}
    >
      <Stack direction="row" spacing={{ xs: 1.25, sm: 2 }} alignItems="flex-start">
        <Box
          sx={{
            width: { xs: 36, sm: 44 },
            height: { xs: 36, sm: 44 },
            borderRadius: 2.5,
            display: "grid", placeItems: "center",
            bgcolor: accentBg, color: iconColor,
            flexShrink: 0,
            "& > svg": { fontSize: { xs: 20, sm: 24 } },
          }}
        >
          {icon}
        </Box>
        <Box sx={{ minWidth: 0, flex: 1, width: "100%" }}>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              letterSpacing: ".06em",
              textTransform: "uppercase",
              fontSize: { xs: ".62rem", sm: ".7rem" },
            }}
          >
            {label}
          </Typography>
          <Typography
            variant="h5"
            // Bewusst KEIN noWrap: in einer Viertelspalte bleiben neben Icon
            // und Innenabstand rund 160 px, und "Nicht erkannt" braucht bei
            // 1.5rem etwa 170 px. Mit noWrap wurde daraus "Nicht erka…" —
            // ausgerechnet die Meldung, die der Betreiber lesen muss. Zwei
            // Zeilen sind hier besser als eine abgeschnittene.
            title={typeof value === "string" ? value : undefined}
            sx={{
              mt: 0.25,
              fontWeight: 600,
              lineHeight: 1.2,
              // Freitext startet kleiner — 40 Zeichen passen sonst auch auf
              // zwei Zeilen nicht. Kurze Statuswerte behalten die Kennzahl-
              // Groesse, damit die Zeile einheitlich aussieht.
              fontSize: wrapValue
                ? { xs: ".95rem", sm: "1.15rem" }
                : { xs: "1.1rem", sm: "1.5rem" },
              // Hoechstens zwei Zeilen, Rest mit Ellipse — sonst waechst eine
              // Karte in der Hoehe und zieht die ganze Zeile mit.
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              // "anywhere" auch fuer kurze Werte — als Netz, nicht als Regel:
              // Browser nehmen zuerst die Wortluecke, "Nicht erkannt" bricht
              // also weiterhin in "Nicht" / "erkannt". Erst wenn ein einzelnes
              // Wort selbst zu breit ist, greift der Bruch im Wort. Ohne das
              // wurde bei schmaler Kachel mitten im Buchstaben abgeschnitten.
              overflowWrap: "anywhere",
            }}
          >
            {loading ? <Skeleton width={60} /> : value}
          </Typography>
          {hint && (
            <Box sx={{ mt: { xs: 0.5, sm: 1 } }}>
              {hint}
            </Box>
          )}
        </Box>
      </Stack>
    </Paper>
  );
}

// Wie lange nach dem Countdown auf die Box gewartet wird, bevor die UI
// aufgibt. 30 x 2 s = eine Minute — laenger als jeder gesunde Start (5 s
// RestartSec + ~6 s), aber kurz genug, dass niemand ewig auf einen Spinner
// starrt, wenn systemd den Dienst wegen StartLimitBurst stillgelegt hat.
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const RESTART_POLL_MS = 2000;
const RESTART_POLL_MAX = 30;

export default function AdminOverview() {
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const [status, setStatus] = useState<AdminStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const s = await api.admin.status();
      setStatus(s);
    } catch { /* ignore */ }
    finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(() => load(true), 15000);
    return () => clearInterval(id);
  }, []);

  const usedPct = status && status.total_mb > 0
    ? Math.max(0, Math.min(100, ((status.total_mb - status.free_mb) / status.total_mb) * 100))
    : 0;
  const diskAccent = usedPct > 90 ? "error" : usedPct > 75 ? "warning" : "success";

  // ── Neustart ───────────────────────────────────────────────────────────────
  const [rsOpen, setRsOpen] = useState(false);
  const [rsBusy, setRsBusy] = useState(false);
  // Restsekunden des Countdowns. 0 heisst: Countdown durch, wir klopfen an.
  const [rsWait, setRsWait] = useState(0);
  // Der Gastgeber bekommt erst den Hinweis, dann die Rueckfrage. Fuer den
  // Besitzer selbst gibt es nichts zu quittieren — er ist der, der Bescheid
  // bekommen soll.
  const [rsAck, setRsAck] = useState(false);
  const rsNotice = !isAdmin && !rsAck;
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);

  // Bewusst eine durchlaufende async-Funktion statt Effekt-Ketten: der Ablauf
  // ist streng seriell (anfordern, warten, anklopfen), und als Schleife liest
  // er sich wie das, was der Gastgeber vor sich sieht.
  const restart = async () => {
    setRsBusy(true);
    try {
      const r = await api.admin.restart();
      if (!r.ok) throw new Error(r.error ?? "Neustart fehlgeschlagen");

      for (let s = r.eta_s ?? 15; s > 0; s--) {
        setRsWait(s);
        await sleep(1000);
      }
      setRsWait(0);

      // Die Box ist erst zurueck, wenn sie antwortet — nicht wenn der
      // Countdown abgelaufen ist. Der Admin-Cookie ueberlebt den Neustart,
      // weil der Flask-Secret-Key auf Platte liegt (_load_or_create_secret_key).
      for (let i = 0; i < RESTART_POLL_MAX; i++) {
        try {
          await api.admin.status();
          setToast({ severity: "success", msg: "Fotobox ist wieder da." });
          setRsOpen(false);
          load(true);
          return;
        } catch {
          await sleep(RESTART_POLL_MS);
        }
      }
      throw new Error(
        "Die Box meldet sich nicht zurück. Bitte am Gerät oder per SSH nachsehen.",
      );
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
      setRsOpen(false);
    } finally {
      setRsBusy(false);
      setRsWait(0);
    }
  };

  return (
    <>
      <Stack spacing={3}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h5" sx={{ fontWeight: 500 }}>
              Übersicht
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Live-Status deiner Fotobox
            </Typography>
          </Box>
          <Button
            startIcon={<RefreshRoundedIcon />}
            onClick={() => load()}
            disabled={refreshing}
            variant="text"
            color="inherit"
            sx={{
              color: "text.secondary",
              flexShrink: 0,
              minWidth: { xs: 40, sm: "auto" },
              px: { xs: 1, sm: 2 },
              "& .MuiButton-startIcon": {
                mr: { xs: 0, sm: 1 },
              },
              "& .button-label": {
                display: { xs: "none", sm: "inline" },
              },
            }}
            aria-label="Aktualisieren"
          >
            <span className="button-label">{refreshing ? "Lade…" : "Aktualisieren"}</span>
          </Button>
        </Stack>

        <Box
          sx={{
            display: "grid",
            gap: { xs: 1.25, sm: 2 },
            // minmax(0, 1fr) statt 1fr: `1fr` ist die Kurzform von
            // minmax(auto, 1fr), und dieses auto-Minimum laesst eine Spalte
            // nicht unter die Min-Content-Breite ihres Inhalts schrumpfen. Ein
            // langer Event-Name steht in einem noWrap-Typography und hat damit
            // eine Min-Content-Breite von mehreren hundert Pixeln — die Spalte
            // sprengte die Zeile und quetschte die drei anderen Karten aus dem
            // Bild. Mit 0 als Minimum greifen Umbruch und Ellipse wieder.
            gridTemplateColumns: {
              xs: "repeat(2, minmax(0, 1fr))",
              sm: "repeat(2, minmax(0, 1fr))",
              lg: "repeat(4, minmax(0, 1fr))",
            },
          }}
        >
          <StatCard
            icon={<CelebrationRoundedIcon />}
            label="Event"
            value={status?.event_name ?? "—"}
            wrapValue
            loading={loading}
            hint={
              <Typography variant="caption" color="text.secondary">
                Aktueller Anzeigename
              </Typography>
            }
          />
          <StatCard
            icon={<PhotoLibraryRoundedIcon />}
            label="Fotos"
            value={status?.photo_count ?? 0}
            loading={loading}
            hint={
              <Typography variant="caption" color="text.secondary">
                {status?.photo_count === 1 ? "Foto in der Galerie" : "Fotos in der Galerie"}
              </Typography>
            }
          />
          <StatCard
            icon={<CameraAltRoundedIcon />}
            label="Kamera"
            accent={status?.camera_ok ? "success" : "error"}
            value={status?.camera_ok ? "Verbunden" : "Nicht erkannt"}
            loading={loading}
            hint={
              <Chip
                size="small"
                variant="outlined"
                icon={status?.camera_ok ? <CheckCircleRoundedIcon /> : <ErrorOutlineRoundedIcon />}
                label={status?.camera_ok ? "USB OK" : "Bitte prüfen"}
                color={status?.camera_ok ? "success" : "error"}
                sx={{ fontSize: ".72rem", height: 22 }}
              />
            }
          />
          <StatCard
            icon={<StorageRoundedIcon />}
            label="Speicher"
            accent={diskAccent}
            value={`${status?.free_gb ?? "—"} GB`}
            loading={loading}
            hint={
              <Tooltip title={`${Math.round(usedPct)}% belegt`}>
                <Box>
                  <LinearProgress
                    variant="determinate"
                    value={usedPct}
                    sx={{
                      height: 6, borderRadius: 3, mt: 0.5,
                      bgcolor: "grey.200",
                      "& .MuiLinearProgress-bar": {
                        backgroundColor:
                          diskAccent === "error"   ? "#d93025" :
                          diskAccent === "warning" ? "#f29900" :
                                                     "#1e8e3e",
                      },
                    }}
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                    von {status?.total_gb ?? "—"} GB frei
                  </Typography>
                </Box>
              </Tooltip>
            }
          />
        </Box>

        <Paper
          elevation={0}
          sx={{
            p: { xs: 2.5, sm: 3 },
            borderRadius: 3,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
            Quick-Tipp
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isAdmin ? (
              <>Stelle Event-Name und Countdown unter <b>Event</b> ein — das Logo deines Kunden
              lädst du unter <b>Logo</b> hoch. Vor jedem Event empfiehlt sich ein
              Foto-Reset unter <b>Wartung</b>.</>
            ) : (
              <>Trage hier den Namen deines Events ein und lade dein eigenes Logo hoch.
              Den Countdown vor dem Auslösen kannst du ebenfalls anpassen.</>
            )}
          </Typography>
        </Paper>

        <Paper
          elevation={0}
          sx={{
            p: { xs: 2.5, sm: 3 },
            borderRadius: 3,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            alignItems={{ xs: "stretch", sm: "center" }}
            justifyContent="space-between"
          >
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.5 }}>
                Fotobox neu starten
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Hilft, wenn die Box am Bildschirm nicht mehr reagiert oder die
                Kamera sich verhakt hat. Fotos bleiben erhalten.
              </Typography>
            </Box>
            <Button
              variant="outlined"
              color="warning"
              startIcon={<RestartAltRoundedIcon />}
              onClick={() => { setRsAck(false); setRsOpen(true); }}
              disabled={rsBusy}
              sx={{ flexShrink: 0 }}
            >
              Neu starten
            </Button>
          </Stack>
        </Paper>
      </Stack>

      <Dialog
        open={rsOpen}
        onClose={rsBusy ? undefined : () => setRsOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <RestartAltRoundedIcon color="warning" />
          {rsNotice ? "Kurz Bescheid geben" : "Fotobox neu starten?"}
        </DialogTitle>
        <DialogContent>
          {rsBusy ? (
            <Stack alignItems="center" spacing={2} sx={{ py: 2 }}>
              <CircularProgress />
              <Typography variant="body2" color="text.secondary" align="center">
                {rsWait > 0
                  ? `Die Box fährt hoch — noch etwa ${rsWait} s.`
                  : "Warte darauf, dass sich die Box zurückmeldet…"}
              </Typography>
            </Stack>
          ) : rsNotice ? (
            <>
              <Alert severity="info" sx={{ mb: 2 }}>
                Bitte sag dem Box-Besitzer Bescheid, bevor du die Fotobox neu
                startest.
              </Alert>
              <Typography variant="body2" color="text.secondary">
                Oft steckt hinter einer stehenden Box etwas, das sich mit einem
                Handgriff lösen lässt — eine ausgegangene Kamera, ein gezogenes
                USB-Kabel. Ein Neustart überdeckt das nur. Wenn ihr euch einig
                seid, geht es hier weiter.
              </Typography>
            </>
          ) : (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Die Box beendet sich und startet von selbst wieder — das dauert
                rund 15 Sekunden. Fotos, Event und Einstellungen bleiben
                unangetastet.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                <b>Dabei geht kurz das WLAN weg</b>, weil der Hotspot mit
                heruntergefahren wird. Dein Handy verbindet sich danach meist
                von allein wieder — diese Seite meldet sich, sobald die Box
                zurück ist.
              </Typography>
            </>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button
            onClick={() => setRsOpen(false)}
            disabled={rsBusy}
            color="inherit"
            sx={{ flex: 1 }}
          >
            Abbrechen
          </Button>
          <Button
            variant="contained"
            color="warning"
            onClick={rsNotice ? () => setRsAck(true) : restart}
            disabled={rsBusy}
            sx={{ flex: 1 }}
          >
            {rsNotice ? "Weiter" : rsBusy ? "Startet…" : "Neu starten"}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!toast}
        autoHideDuration={2800}
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
