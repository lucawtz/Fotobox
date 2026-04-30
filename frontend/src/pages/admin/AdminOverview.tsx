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

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  accent?: "primary" | "success" | "warning" | "error";
  loading?: boolean;
}

function StatCard({ icon, label, value, hint, accent = "primary", loading }: StatCardProps) {
  const accentColor =
    accent === "success" ? "rgba(110,200,140,0.18)" :
    accent === "warning" ? "rgba(232,180,80,0.18)" :
    accent === "error"   ? "rgba(224,83,60,0.18)"  :
                           "rgba(212,168,106,0.18)";
  const iconColor =
    accent === "success" ? "#7fd99a" :
    accent === "warning" ? "#f0c267" :
    accent === "error"   ? "#ff8870" :
                           "#f0c98a";

  return (
    <Paper
      elevation={0}
      sx={{
        p: { xs: 2, sm: 2.5 },
        borderRadius: 3,
        border: "1px solid",
        borderColor: "divider",
        height: "100%",
      }}
    >
      <Stack direction="row" spacing={2} alignItems="flex-start">
        <Box
          sx={{
            width: 44, height: 44, borderRadius: 2.5,
            display: "grid", placeItems: "center",
            bgcolor: accentColor, color: iconColor,
            flexShrink: 0,
          }}
        >
          {icon}
        </Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: ".06em", textTransform: "uppercase", fontSize: ".7rem" }}>
            {label}
          </Typography>
          <Typography variant="h5" sx={{ mt: 0.25, fontWeight: 600, lineHeight: 1.1 }}>
            {loading ? <Skeleton width={80} /> : value}
          </Typography>
          {hint && (
            <Box sx={{ mt: 1 }}>
              {hint}
            </Box>
          )}
        </Box>
      </Stack>
    </Paper>
  );
}

export default function AdminOverview() {
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
        <Box>
          <Typography variant="h5" sx={{ fontFamily: '"Playfair Display", serif', fontWeight: 600 }}>
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
          sx={{ color: "text.secondary" }}
        >
          {refreshing ? "Lade…" : "Aktualisieren"}
        </Button>
      </Stack>

      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" },
        }}
      >
        <StatCard
          icon={<CelebrationRoundedIcon />}
          label="Event"
          value={status?.event_name ?? "—"}
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
                    bgcolor: "rgba(255,255,255,0.05)",
                    "& .MuiLinearProgress-bar": {
                      background:
                        diskAccent === "error"   ? "linear-gradient(90deg,#e0533c,#ff8870)" :
                        diskAccent === "warning" ? "linear-gradient(90deg,#e0a33c,#f0c267)" :
                                                   "linear-gradient(90deg,#7fd99a,#a3e6b8)",
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
          Stelle Event-Name und Countdown unter <b>Event</b> ein — das Logo deines Kunden
          lädst du unter <b>Logo</b> hoch. Vor jedem Event empfiehlt sich ein
          Foto-Reset unter <b>Wartung</b>.
        </Typography>
      </Paper>
    </Stack>
  );
}
