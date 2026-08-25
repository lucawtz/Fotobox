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
} from "@mui/material";
import PhotoLibraryRoundedIcon from "@mui/icons-material/PhotoLibraryRounded";
import StorageRoundedIcon from "@mui/icons-material/StorageRounded";
import CameraAltRoundedIcon from "@mui/icons-material/CameraAltRounded";
import CelebrationRoundedIcon from "@mui/icons-material/CelebrationRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";
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

  return (
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
    </Stack>
  );
}
