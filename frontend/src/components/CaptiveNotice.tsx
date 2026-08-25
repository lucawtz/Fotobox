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
import WifiRoundedIcon from "@mui/icons-material/WifiRounded";
import { galleryAddress, isCaptivePopup, isIOS, leaveCaptivePopup } from "../captive";

/** Wie der Gast seinen richtigen Browser nennt. */
const browserName = () => (isIOS() ? "Safari" : "deinem Browser");

/**
 * Was unmittelbar nach dem Tippen passiert — und zwar so, wie es wirklich
 * aussieht.
 *
 * leaveCaptivePopup() versucht erst den Sprung in den echten Browser; scheitert
 * der (auf iOS die Regel), landet der Gast auf der Erfolgsseite, die sein
 * Betriebssystem sehen will. Auf dem Bildschirm steht dann nur "Success", und
 * genau an dieser Stelle sind Gaeste bisher stehengeblieben: die Seite sieht
 * aus wie ein Fehler, dabei ist sie das Ziel. Deshalb wird sie hier
 * angekuendigt, statt sie zu ueberraschen.
 */
const finishHint = () =>
  isIOS()
    ? 'Es erscheint kurz eine Seite mit „Success“ — tipp dann oben auf ✓.'
    : "Das Fenster schließt sich, und du bist normal im WLAN.";

/** Nummerierter Schritt im Dialog. */
function Step({ n, title, children }: {
  n: number; title: string; children: React.ReactNode;
}) {
  return (
    <Box sx={{ display: "flex", gap: 1.5 }}>
      <Box
        sx={{
          flex: "0 0 auto",
          width: 28,
          height: 28,
          borderRadius: "50%",
          bgcolor: "primary.main",
          color: "primary.contrastText",
          display: "grid",
          placeItems: "center",
          fontWeight: 700,
          fontSize: "0.95rem",
        }}
      >
        {n}
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
          {title}
        </Typography>
        {children}
      </Box>
    </Box>
  );
}

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
        So kommst du an dein Foto
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Du bist gerade im WLAN-Anmeldefenster deines Handys. Hier kann
            dein Handy keine Bilder speichern — ein angetipptes Foto
            verschwindet, statt in deinen Fotos zu landen.
          </Typography>

          <Step n={1} title="WLAN fertig verbinden">
            <Typography variant="body2" sx={{ mb: 1 }}>
              Tipp unten auf <strong>Verbinden</strong>. {finishHint()}
            </Typography>
            <Button
              variant="contained"
              fullWidth
              onClick={go}
              disabled={busy}
              startIcon={<WifiRoundedIcon />}
            >
              Verbinden
            </Button>
          </Step>

          <Step n={2} title="Foto holen">
            <Typography variant="body2">
              Halt die Kamera auf den <strong>QR-Code an der Box</strong> —
              neben deinem Foto. Er öffnet das Bild in {browserName()}, und
              dort funktioniert Speichern ganz normal.
            </Typography>
          </Step>

          <Typography variant="body2" color="text.secondary">
            Kein Code zur Hand? In {browserName()} diese Adresse eingeben:
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
        <Button onClick={onClose} disabled={busy}>Schließen</Button>
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
            Zeigen
          </Button>
        }
        sx={{
          mb: { xs: 1.25, sm: 2 },
          alignItems: "center",
          "& .MuiAlert-message": { py: 0.5 },
        }}
      >
        Dieses WLAN-Fenster kann keine Fotos speichern. In zwei Schritten
        kommst du an deine Bilder.
      </Alert>
      <CaptiveDialog open={ask} onClose={() => setAsk(false)} />
    </>
  );
}
