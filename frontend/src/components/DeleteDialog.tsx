import { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Stack,
  Typography,
  Alert,
} from "@mui/material";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import { api, Photo } from "../api";
import { useSessionRole } from "../sessionRole";

interface Props {
  open: boolean;
  photo: Pick<Photo, "event" | "filename"> | null;
  onClose: () => void;
  onDeleted: () => void;
}

export default function DeleteDialog({ open, photo, onClose, onDeleted }: Props) {
  const role = useSessionRole();
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Wer eingeloggt ist, hat die PIN schon einmal getippt — der Server nimmt
  // die Session. `undefined` heisst "wird noch geprueft": dann den Button
  // kurz sperren, statt das PIN-Feld einzublenden und gleich wieder
  // wegzunehmen.
  const checking = role === undefined;
  const needsPin = role === null;

  const reset = () => { setPin(""); setError(null); setBusy(false); };
  const close = () => { reset(); onClose(); };

  const submit = async () => {
    if (!photo || checking || (needsPin && pin.length < 1)) return;
    setBusy(true); setError(null);
    try {
      const r = await api.delete(photo, needsPin ? pin : undefined);
      if (!r.ok) {
        setError(r.error ?? "Löschen fehlgeschlagen");
        setBusy(false);
        return;
      }
      reset();
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={busy ? undefined : close} fullWidth maxWidth="xs">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25, pb: 1 }}>
        <DeleteOutlineRoundedIcon color="error" />
        Foto löschen?
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Dieser Vorgang kann nicht rückgängig gemacht werden.
            {needsPin && " Bitte Admin-PIN eingeben."}
          </Typography>
          {error && <Alert severity="error" variant="outlined">{error}</Alert>}
          {needsPin && (
            <TextField
              autoFocus
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="••••"
              fullWidth
              inputProps={{
                style: { textAlign: "center", letterSpacing: "0.4em", fontSize: "1.1rem" },
                maxLength: 12,
              }}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              disabled={busy}
            />
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ p: 2, gap: 1 }}>
        <Button onClick={close} disabled={busy} color="inherit" sx={{ flex: 1 }}>
          Abbrechen
        </Button>
        <Button
          onClick={submit}
          disabled={busy || checking || (needsPin && pin.length === 0)}
          variant="contained"
          color="error"
          sx={{ flex: 1 }}
        >
          {busy ? "Lösche…" : "Löschen"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
