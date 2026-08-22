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
  Checkbox,
  FormGroup,
  FormControlLabel,
  Divider,
} from "@mui/material";
import BuildRoundedIcon from "@mui/icons-material/BuildRounded";
import DeleteForeverRoundedIcon from "@mui/icons-material/DeleteForeverRounded";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import CleaningServicesRoundedIcon from "@mui/icons-material/CleaningServicesRounded";
import { api, HandoverSteps } from "../../api";
import SettingsCard from "./SettingsCard";

const CONFIRM = "LOESCHEN";

const HANDOVER_ITEMS: { key: keyof HandoverSteps; label: string; hint: string }[] = [
  { key: "branding",  label: "Event & Design zurücksetzen",
    hint: "Event-Name, Untertitel, Countdown und Farbschema auf Standard." },
  { key: "logo",      label: "Logo entfernen",
    hint: "Der Homescreen zeigt danach wieder dein Standard-Logo." },
  { key: "photos",    label: "Alle Fotos löschen",
    hint: "Samt Thumbnails und Vorschauen. Nicht rückgängig zu machen." },
  { key: "new_event", label: "Neues Event starten",
    hint: "Die nächste Feier bekommt einen frischen Ordner." },
];

export default function AdminMaintenance() {
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error"; msg: string } | null>(null);
  const [steps, setSteps] = useState<HandoverSteps>({
    branding: true, logo: true, photos: true, new_event: true,
  });
  const [hoOpen, setHoOpen] = useState(false);
  const [hoConfirm, setHoConfirm] = useState("");
  const [hoBusy, setHoBusy] = useState(false);

  const picked = HANDOVER_ITEMS.filter((it) => steps[it.key]);
  // Der Tippzwang gilt nur fuer die eine Aktion, die nichts wiederherstellt.
  const hoReady = picked.length > 0 && (!steps.photos || hoConfirm === CONFIRM);

  const handover = async () => {
    setHoBusy(true);
    try {
      const r = await api.admin.handover(steps, hoConfirm);
      if (!r.ok) throw new Error(r.error ?? "Zurücksetzen fehlgeschlagen");
      const parts: string[] = [];
      if (r.done.branding) parts.push("Event & Design zurückgesetzt");
      if (r.done.logo) parts.push("Logo entfernt");
      if (r.done.photos) parts.push(`${r.removed} Foto${r.removed === 1 ? "" : "s"} gelöscht`);
      if (r.folder) parts.push(`neues Event: ${r.folder}`);
      setToast({ severity: "success", msg: parts.join(", ") });
      setHoOpen(false);
      setHoConfirm("");
    } catch (e) {
      setToast({ severity: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally { setHoBusy(false); }
  };

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
          icon={<CleaningServicesRoundedIcon />}
          title="Für nächste Vermietung vorbereiten"
          description="Räumt in einem Durchgang weg, was vom letzten Gastgeber übrig ist."
        >
          <FormGroup>
            {HANDOVER_ITEMS.map((it) => (
              <FormControlLabel
                key={it.key}
                sx={{ alignItems: "flex-start", mr: 0, mb: 1 }}
                control={
                  <Checkbox
                    checked={steps[it.key]}
                    onChange={(e) =>
                      setSteps((s) => ({ ...s, [it.key]: e.target.checked }))
                    }
                    color={it.key === "photos" ? "error" : "primary"}
                    sx={{ pt: 0.5 }}
                  />
                }
                label={
                  <Box sx={{ py: 0.25 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {it.label}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {it.hint}
                    </Typography>
                  </Box>
                }
              />
            ))}
          </FormGroup>

          <Box
            sx={{
              mt: 1, p: 2, borderRadius: 2.5,
              bgcolor: "grey.50",
              border: "1px solid", borderColor: "divider",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              WLAN-Zugangsdaten und PINs bleiben unverändert — die vergibst du
              selbst unter <b>WLAN</b> und <b>Event</b>.
            </Typography>
          </Box>

          <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
            <Button
              variant="contained"
              startIcon={<CleaningServicesRoundedIcon />}
              disabled={picked.length === 0 || hoBusy}
              onClick={() => { setHoConfirm(""); setHoOpen(true); }}
            >
              Box vorbereiten
            </Button>
          </Box>
        </SettingsCard>

        <Divider />

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

      <Dialog
        open={hoOpen}
        onClose={hoBusy ? undefined : () => setHoOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <CleaningServicesRoundedIcon color="primary" />
          Box vorbereiten?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Es passiert genau das:
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {picked.map((it) => (
              <Typography
                key={it.key}
                component="li"
                variant="body2"
                sx={{ mb: 0.5, color: it.key === "photos" ? "error.main" : "text.primary" }}
              >
                {it.label}
              </Typography>
            ))}
          </Box>

          {steps.photos && (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2, mb: 1 }}>
                Die Fotos sind danach weg. Tippe <b>{CONFIRM}</b> ein, um zu
                bestätigen.
              </Typography>
              <TextField
                value={hoConfirm}
                onChange={(e) => setHoConfirm(e.target.value.toUpperCase())}
                fullWidth
                placeholder={CONFIRM}
                autoFocus
                disabled={hoBusy}
                inputProps={{ style: { letterSpacing: ".15em", fontFamily: "monospace" } }}
              />
            </>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button onClick={() => setHoOpen(false)} disabled={hoBusy} color="inherit" sx={{ flex: 1 }}>
            Abbrechen
          </Button>
          <Button
            variant="contained"
            color={steps.photos ? "error" : "primary"}
            disabled={hoBusy || !hoReady}
            onClick={handover}
            sx={{ flex: 1 }}
          >
            {hoBusy ? "Räume auf…" : "Vorbereiten"}
          </Button>
        </DialogActions>
      </Dialog>

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
