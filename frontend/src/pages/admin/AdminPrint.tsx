import { useEffect, useState } from "react";
import {
  Stack,
  Box,
  Typography,
  Button,
  Alert,
  Skeleton,
  Switch,
  MenuItem,
  TextField,
  Chip,
  FormControlLabel,
} from "@mui/material";
import PrintRoundedIcon from "@mui/icons-material/PrintRounded";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import { api, AdminConfig, PrinterInfo } from "../../api";
import SettingsCard from "./SettingsCard";

const MODES = [
  { value: "auto",  label: "Automatisch",
    hint: "Einzelfotos randlos, Collagen vollständig mit weißem Rand. Empfohlen." },
  { value: "cover", label: "Immer randlos",
    hint: "Füllt das Papier immer aus. Bei Collagen wird oben und unten abgeschnitten." },
  { value: "fit",   label: "Immer vollständig",
    hint: "Zeigt das ganze Bild, lässt dafür einen weißen Rand." },
];

export default function AdminPrint() {
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [info, setInfo] = useState<PrinterInfo | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [printer, setPrinter] = useState("");
  const [copies, setCopies] = useState(1);
  const [mode, setMode] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ sev: "success" | "error"; msg: string } | null>(null);

  const loadPrinters = () => api.admin.printers().then(setInfo).catch(() => setInfo(null));

  useEffect(() => {
    api.admin.config.get().then((c) => {
      setCfg(c);
      setEnabled(c.print_enabled ?? true);
      setPrinter(c.printer_name ?? "");
      setCopies(c.print_copies ?? 1);
      setMode(c.print_mode ?? "auto");
    });
    loadPrinters();
  }, []);

  const dirty = !!cfg && (
    enabled !== (cfg.print_enabled ?? true) ||
    printer !== (cfg.printer_name ?? "") ||
    copies !== (cfg.print_copies ?? 1) ||
    mode !== (cfg.print_mode ?? "auto")
  );

  const save = async () => {
    setBusy(true);
    try {
      await api.admin.config.save({
        print_enabled: enabled,
        printer_name: printer,
        print_copies: copies,
        print_mode: mode as AdminConfig["print_mode"],
      });
      setCfg({ ...cfg!, print_enabled: enabled, printer_name: printer,
               print_copies: copies, print_mode: mode as AdminConfig["print_mode"] });
      setToast({ sev: "success", msg: "Druckeinstellungen gespeichert" });
      loadPrinters();
    } catch (e) {
      setToast({ sev: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally { setBusy(false); }
  };

  const st = info?.status;

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h5" sx={{ fontWeight: 500 }}>Drucken</Typography>
        <Typography variant="body2" color="text.secondary">
          Fotodrucker für den „Drucken"-Knopf an der Box
        </Typography>
      </Box>

      {/* Zustand zuerst: die häufigste Frage am Event-Tag ist "geht der Drucker?" */}
      {info === null ? (
        <Skeleton variant="rounded" height={64} />
      ) : st?.available ? (
        <Alert severity="success">
          Drucker <strong>{st.printer}</strong> ist bereit. Der „Drucken"-Knopf
          wird auf dem Boxschirm angezeigt.
        </Alert>
      ) : (
        <Alert severity="warning">
          {st?.message ?? "Drucksystem nicht erreichbar"}. Solange kein Drucker
          bereit ist, blendet die Box den „Drucken"-Knopf aus — ein Knopf, der
          nichts tut, verwirrt Gäste mehr, als dass er hilft.
        </Alert>
      )}

      <SettingsCard
        icon={<PrintRoundedIcon />}
        title="Drucker"
        description="Leer lassen = CUPS-Standarddrucker verwenden."
      >
        {info === null ? <Skeleton variant="rounded" height={56} /> : (
          <Stack spacing={2}>
            <FormControlLabel
              control={<Switch checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />}
              label="Drucken aktiviert"
            />
            <TextField
              select
              fullWidth
              label="Zielgerät"
              value={printer}
              onChange={(e) => setPrinter(e.target.value)}
              disabled={!enabled}
              helperText={
                info.printers.length === 0
                  ? "CUPS kennt keinen Drucker. Einrichtung siehe README."
                  : `${info.printers.length} Drucker gefunden${info.default ? ` · Standard: ${info.default}` : ""}`
              }
            >
              <MenuItem value="">
                <em>Standarddrucker verwenden</em>
              </MenuItem>
              {info.printers.map((p) => (
                <MenuItem key={p.name} value={p.name}>
                  {p.name}
                  <Chip
                    size="small"
                    label={p.state}
                    color={p.ready ? "success" : "warning"}
                    sx={{ ml: 1 }}
                  />
                </MenuItem>
              ))}
            </TextField>
            <Button
              size="small"
              startIcon={<RefreshRoundedIcon />}
              onClick={loadPrinters}
              sx={{ alignSelf: "flex-start" }}
            >
              Druckerliste neu laden
            </Button>
          </Stack>
        )}
      </SettingsCard>

      <SettingsCard
        icon={<TuneRoundedIcon />}
        title="Ausgabe"
        description="Wie das Foto auf das Papier gerechnet wird."
      >
        {cfg ? (
          <Stack spacing={2}>
            <TextField
              select
              fullWidth
              label="Seitenanpassung"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              disabled={!enabled}
              helperText={MODES.find((m) => m.value === mode)?.hint}
            >
              {MODES.map((m) => (
                <MenuItem key={m.value} value={m.value}>{m.label}</MenuItem>
              ))}
            </TextField>
            <TextField
              type="number"
              label="Kopien pro Druck"
              value={copies}
              onChange={(e) => setCopies(Math.max(1, Math.min(9, Number(e.target.value) || 1)))}
              disabled={!enabled}
              inputProps={{ min: 1, max: 9 }}
              sx={{ maxWidth: 200 }}
              helperText="1–9"
            />
          </Stack>
        ) : <Skeleton variant="rounded" height={56} />}
      </SettingsCard>

      <Alert severity="info" variant="outlined">
        Papierformat und Treiberoptionen (z.&nbsp;B. randlos beim Canon Selphy)
        stehen in <code>config.py</code> unter <code>print_media</code>,
        <code> print_size_mm</code> und <code>print_options</code>. Die für den
        angeschlossenen Drucker gültigen Werte listet
        {" "}<code>lpoptions -p &lt;drucker&gt; -l</code> auf.
      </Alert>

      <Box sx={{ display: "flex", justifyContent: { xs: "stretch", sm: "flex-end" }, gap: 1.5 }}>
        <Button
          disabled={!dirty || busy}
          color="inherit"
          onClick={() => {
            if (!cfg) return;
            setEnabled(cfg.print_enabled ?? true);
            setPrinter(cfg.printer_name ?? "");
            setCopies(cfg.print_copies ?? 1);
            setMode(cfg.print_mode ?? "auto");
          }}
        >
          Verwerfen
        </Button>
        <Button disabled={!dirty || busy} onClick={save} variant="contained">
          {busy ? "Speichere…" : "Speichern"}
        </Button>
      </Box>

      {toast && (
        <Alert severity={toast.sev} onClose={() => setToast(null)}>{toast.msg}</Alert>
      )}
    </Stack>
  );
}
