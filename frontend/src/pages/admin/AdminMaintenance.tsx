import { useState } from "react";
import {
  Stack,
  Box,
  Button,
  Typography,
  Snackbar,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from "@mui/material";
import BuildRoundedIcon from "@mui/icons-material/BuildRounded";
import DeleteForeverRoundedIcon from "@mui/icons-material/DeleteForeverRounded";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import { api } from "../../api";
import SettingsCard from "./SettingsCard";

const CONFIRM = "LOESCHEN";

export default function AdminMaintenance() {
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);

  const reset = async () => {
    setBusy(true);
    try {
      const r = await api.admin.reset(confirmText);
      if (!r.ok) throw new Error(r.error ?? "Reset fehlgeschlagen");
      setToast({ severity: "success", msg: `${r.removed ?? 0} Foto${r.removed === 1 ? "" : "s"} gelöscht` });
      setOpen(false);
      setConfirmText("");
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally { setBusy(false); }
  };

  return (
    <>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            Wartung
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Aufräumen vor dem nächsten Event
          </Typography>
        </Box>

        <SettingsCard
          icon={<BuildRoundedIcon />}
          title="Foto-Reset"
          description="Löscht alle Fotos und Thumbnails dauerhaft. Konfiguration bleibt erhalten."
        >
          <Box
            sx={{
              p: 2.5,
              borderRadius: 2.5,
              bgcolor: "#fce8e6",
              border: "1px solid #f6cfcb",
              display: "flex",
              alignItems: "flex-start",
              gap: 2,
            }}
          >
            <WarningAmberRoundedIcon sx={{ color: "#c5221f", mt: 0.25 }} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ color: "#a50e0e", fontWeight: 600 }}>
                Achtung: Vorgang ist nicht rückgängig zu machen
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5, color: "#5f1a17" }}>
                Erstelle vorher unbedingt ein Backup, falls die Fotos noch
                gebraucht werden.
              </Typography>
            </Box>
          </Box>

          <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
            <Button
              variant="contained"
              color="error"
              startIcon={<DeleteForeverRoundedIcon />}
              onClick={() => setOpen(true)}
            >
              Alle Fotos löschen
            </Button>
          </Box>
        </SettingsCard>
      </Stack>

      <Dialog open={open} onClose={busy ? undefined : () => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <DeleteForeverRoundedIcon color="error" />
          Wirklich alle Fotos löschen?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Tippe <b>{CONFIRM}</b> ein, um zu bestätigen.
          </Typography>
          <TextField
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value.toUpperCase())}
            fullWidth
            placeholder={CONFIRM}
            autoFocus
            disabled={busy}
            inputProps={{ style: { letterSpacing: ".15em", fontFamily: "monospace" } }}
          />
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button onClick={() => setOpen(false)} disabled={busy} color="inherit" sx={{ flex: 1 }}>
            Abbrechen
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={busy || confirmText !== CONFIRM}
            onClick={reset}
            sx={{ flex: 1 }}
          >
            {busy ? "Lösche…" : "Löschen"}
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
