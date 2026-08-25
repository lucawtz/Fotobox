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
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import QrCodeScannerRoundedIcon from "@mui/icons-material/QrCodeScannerRounded";
import { galleryAddress, isCaptivePopup, isIOS, leaveCaptivePopup } from "../captive";

/** Wie der Gast seinen richtigen Browser nennt. */
const browserName = () => (isIOS() ? "Safari" : "deinem Browser");

interface DialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Erklaert, wie der Gast an sein Bild kommt.
 *
 * Der Hauptweg ist der Code neben dem Foto auf dem Boxschirm, nicht mehr der
 * Wechsel von hier aus. Grund ist eine Eigenheit der Handys: ein mit der
 * Kamera gescannter Code oeffnet sich IMMER im echten Browser, nie in diesem
 * Fenster — und dort funktioniert Sichern ohne Umweg. Der Wechsel per
 * leaveCaptivePopup() bleibt darunter stehen, weil er fuer die Galerie als
 * Ganzes (ZIP, mehrere Bilder) weiterhin gebraucht wird. Er ist nur nicht
 * mehr das Erste, was der Gast lesen soll: bei manchen Geraeten schliesst
 * sich dabei nur das Fenster, und dann steht er vor einer Adresse, die er
 * abtippen muss.
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
        <PhotoCameraRoundedIcon color="primary" />
        Foto speichern
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Du siehst die Galerie gerade im WLAN-Anmeldefenster deines Handys.
            Das Fenster kann keine Fotos sichern — ein angetipptes Bild
            verschwindet dort, statt in deinen Fotos zu landen.
          </Typography>
          <Alert severity="success" icon={<QrCodeScannerRoundedIcon />}>
            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
              Am schnellsten: Code am Boxschirm scannen
            </Typography>
            <Typography variant="body2">
              Neben deinem Foto auf der Box steht ein QR-Code. Scanne ihn mit
              der Kamera — er öffnet genau dieses Bild in {browserName()}, und
              dort funktioniert Sichern ganz normal.
            </Typography>
          </Alert>
          <Typography variant="body2" color="text.secondary">
            Oder die ganze Galerie hierher holen: „Öffnen“ wechselt nach{" "}
            {browserName()}. Schließt sich stattdessen nur dieses Fenster,
            {" "}{browserName()} selbst öffnen und diese Adresse eingeben.
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
        icon={<QrCodeScannerRoundedIcon fontSize="inherit" />}
        action={
          <Button color="inherit" size="small" onClick={() => setAsk(true)}>
            Wie?
          </Button>
        }
        sx={{
          mb: { xs: 1.25, sm: 2 },
          alignItems: "center",
          "& .MuiAlert-message": { py: 0.5 },
        }}
      >
        Bild speichern? Den Code neben deinem Foto am Boxschirm scannen —
        dieses WLAN-Fenster kann keine Bilder sichern.
      </Alert>
      <CaptiveDialog open={ask} onClose={() => setAsk(false)} />
    </>
  );
}
