import { Box, Button, Divider, Stack, Typography } from "@mui/material";
import InstagramIcon from "@mui/icons-material/Instagram";
import EventAvailableRoundedIcon from "@mui/icons-material/EventAvailableRounded";
import { api, OwnerLinks as Links } from "../api";

/** "https://instagram.com/foo/" → "@foo". Fallback: "Instagram". */
const handleOf = (url: string): string => {
  const s = url.trim().replace(/\/+$/, "");
  const at = s.split("instagram.com/")[1];
  if (at) {
    const handle = at.split("/")[0].split("?")[0];
    if (handle) return `@${handle}`;
  }
  return s.startsWith("@") ? s : "Instagram";
};

/**
 * Instagram-/Buchungs-Links am Ende der Galerie.
 *
 * Der Gast hat das Handy beim Fotos-Holen ohnehin schon in der Hand — das
 * ist die Stelle mit der geringsten Hürde, ganz ohne zweiten Scan. Am
 * Boxbildschirm geht es nur über die Mini-QR-Codes (ui.py), weil der
 * Bildschirm kein Touchscreen ist.
 *
 * Die Buttons zeigen bewusst auf /go/ und nicht auf die Ziel-URL: wer diese
 * Seite sieht, hängt im Fotobox-WLAN, und dort löst der Captive-DNS jede
 * Domain auf die Box auf. /go/ prüft erst, ob das Handy überhaupt nach
 * draußen kommt, und erklärt sonst den Weg.
 */
export default function OwnerLinks({ links }: { links: Links | null }) {
  const insta = links?.instagram_url?.trim() || "";
  const booking = links?.booking_url?.trim() || "";
  if (!insta && !booking) return null;

  return (
    <Box sx={{ mt: { xs: 4, sm: 6 }, textAlign: "center" }}>
      <Divider sx={{ mb: { xs: 2.5, sm: 3 } }} />
      <Typography
        variant="body2"
        sx={{ color: "text.secondary", mb: 2, fontSize: { xs: ".85rem", sm: ".9rem" } }}
      >
        Gefällt dir die Fotobox?
      </Typography>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.25}
        justifyContent="center"
        sx={{ px: { xs: 2, sm: 0 } }}
      >
        {booking && (
          <Button
            variant="contained"
            disableElevation
            href={api.goUrl("termin")}
            // Neuer Tab (beide Buttons): der Gast ist zum Fotos-Holen
            // hier und soll die Galerie nicht verlieren, nur weil er kurz
            // rausspringt. rel schneidet den window.opener-Zugriff der
            // fremden Seite ab.
            target="_blank"
            rel="noopener noreferrer"
            startIcon={<EventAvailableRoundedIcon />}
            sx={{ borderRadius: 2, textTransform: "none", fontWeight: 600, px: 2.5 }}
          >
            {links?.booking_label?.trim() || "Termin buchen"}
          </Button>
        )}
        {insta && (
          <Button
            variant="outlined"
            href={api.goUrl("instagram")}
            target="_blank"
            rel="noopener noreferrer"
            startIcon={<InstagramIcon />}
            sx={{ borderRadius: 2, textTransform: "none", fontWeight: 500, px: 2.5 }}
          >
            {handleOf(insta)}
          </Button>
        )}
      </Stack>
    </Box>
  );
}
