import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import OpenInBrowserRoundedIcon from "@mui/icons-material/OpenInBrowserRounded";
import { galleryAddress, isCaptivePopup, isIOS, leaveCaptivePopup } from "../captive";

/** Wie der Gast seinen richtigen Browser nennt. */
const browserName = () => (isIOS() ? "Safari" : "deinem Browser");

interface DialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Erklaert den Wechsel und stoesst ihn an. Bewusst mit Adresse zum Abtippen:
 * bei manchen Geraeten schliesst sich das Popup einfach, statt den Browser
 * mitzubringen — dann muss der Gast wissen, wohin.
 */
export function CaptiveDialog({ open, onClose }: DialogProps) {
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setBusy(true);
    await leaveCaptivePopup();
    // Kein setBusy(false): ab hier verlaesst die Seite das Popup. Bliebe der
    // Gast wider Erwarten hier, waere ein zweiter Versuch ohnehin derselbe.
  };

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="xs">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25, pb: 1 }}>
        <OpenInBrowserRoundedIcon color="primary" />
        In {browserName()} öffnen
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Du siehst die Galerie gerade im WLAN-Anmeldefenster deines Handys.
            Das Fenster kann keine Fotos in deine Bilder speichern — deshalb
            verschwindet ein angetipptes Foto dort, statt gesichert zu werden.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            „Öffnen“ holt die Galerie nach {browserName()}. Schließt sich
            stattdessen nur dieses Fenster: {browserName()} selbst öffnen und
            diese Adresse eingeben.
          </Typography>
          <Box
            sx={{
              textAlign: "center",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: "1.15rem",
              fontWeight: 600,
              py: 1.25,
              borderRadius: 2,
              bgcolor: "action.hover",
              userSelect: "all",
            }}
          >
            {galleryAddress()}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>Abbrechen</Button>
        <Button variant="contained" onClick={go} disabled={busy}>Öffnen</Button>
      </DialogActions>
    </Dialog>
  );
}

/**
 * Hinweisstreifen ueber der Galerie — nur im Captive-Popup. Im richtigen
 * Browser rendert die Komponente nichts.
 */
export default function CaptiveBanner() {
  const [ask, setAsk] = useState(false);
  if (!isCaptivePopup()) return null;
  return (
    <>
      <Alert
        severity="info"
        icon={<OpenInBrowserRoundedIcon fontSize="inherit" />}
        action={
          <Button color="inherit" size="small" onClick={() => setAsk(true)}>
            Öffnen
          </Button>
        }
        sx={{
          mb: { xs: 1.25, sm: 2 },
          alignItems: "center",
          "& .MuiAlert-message": { py: 0.5 },
        }}
      >
        Zum Speichern der Fotos in {browserName()} öffnen — dieses
        WLAN-Fenster kann keine Bilder sichern.
      </Alert>
      <CaptiveDialog open={ask} onClose={() => setAsk(false)} />
    </>
  );
}
