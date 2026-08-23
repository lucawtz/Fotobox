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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from "@mui/material";
import PrintRoundedIcon from "@mui/icons-material/PrintRounded";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import FactCheckRoundedIcon from "@mui/icons-material/FactCheckRounded";
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

// CUPS-Zustaende uebersetzen. printing._printer_states liefert das englische
// Wort aus `lpstat -p` durch (idle | printing | disabled) — in einer deutschen
// Oberflaeche stand da vorher schlicht "idle".
//
// Sonderfall "unknown": das heisst NICHT "Drucker kaputt", sondern "lpstat hat
// nicht auf Englisch geantwortet, der Zustand ist nicht auslesbar" (siehe
// printing.list_printers). Deshalb blieb `ready` dort bewusst true — der
// gruene Erfolgs-Chip war trotzdem falsch, denn zugesichert ist hier nichts.
// Neutral grau sagt das Richtige: unbekannt, wird aber angeboten.
const STATE_LABEL: Record<string, { label: string; color: "success" | "warning" | "info" | "default"; title?: string }> = {
  idle:     { label: "bereit",       color: "success" },
  printing: { label: "druckt",       color: "info"    },
  disabled: { label: "deaktiviert",  color: "warning",
              title: "In CUPS deaktiviert — dieser Drucker nimmt keine Auftraege an." },
  unknown:  { label: "Status unbekannt", color: "default",
              title: "CUPS meldet den Zustand nicht auf Englisch, deshalb ist er "
                   + "nicht auslesbar. Drucken wird trotzdem angeboten — ein "
                   + "echter Fehler erscheint dann beim Druckversuch." },
};

/** Fallback fuer Zustaende, die CUPS ausser den vier bekannten liefert. */
const stateChip = (state: string) =>
  STATE_LABEL[state] ?? { label: state, color: "default" as const };

export default function AdminPrint() {
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [info, setInfo] = useState<PrinterInfo | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [printer, setPrinter] = useState("");
  const [copies, setCopies] = useState(1);
  const [mode, setMode] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testBusy, setTestBusy] = useState(false);
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

  const runTest = async () => {
    setTestBusy(true);
    try {
      const r = await api.admin.printTest();
      setToast(r.ok
        ? { sev: "success", msg: r.message ?? "Testseite wird gedruckt" }
        : { sev: "error", msg: r.error ?? "Testdruck fehlgeschlagen" });
      // Nach einem Fehlschlag hat sich der Druckerzustand meist geaendert
      // (Papier leer, Deckel offen) — die Anzeige oben soll das mitbekommen.
      loadPrinters();
    } catch (e) {
      setToast({ sev: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setTestBusy(false);
      setTestOpen(false);
    }
  };

  const st = info?.status;

  // Der Testdruck nimmt die gespeicherte Config vom Server, nicht das Formular
  // hier. Bei ungesicherten Aenderungen wuerde man also etwas anderes testen,
  // als man gerade sieht — deshalb erst speichern.
  const testBlocked =
    dirty            ? "Erst speichern — getestet wird mit den gespeicherten Einstellungen."
    : !enabled       ? "Drucken ist ausgeschaltet."
    : !st?.available ? "Es ist kein Drucker bereit."
    : null;

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
      ) : st?.available && st.state === "unknown" ? (
        // Angeboten, aber nicht bestaetigt: gruen waere hier zu viel
        // versprochen — CUPS hat den Zustand nicht preisgegeben.
        <Alert severity="info">
          Drucker <strong>{st.printer}</strong> ist eingerichtet, sein Zustand
          lässt sich aber nicht auslesen (CUPS antwortet nicht auf Englisch).
          Der „Drucken"-Knopf wird angezeigt — ob wirklich Papier kommt, zeigt
          erst der erste Druckversuch.
        </Alert>
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
                  {/* minWidth 0 + Ellipse: CUPS-Namen wie
                      "Canon_SELPHY_CP1500_5640_series__Dachboden_" sind lang,
                      und der Chip soll nicht aus der Zeile geschoben werden. */}
                  <Box component="span" sx={{ minWidth: 0, flex: 1, overflow: "hidden",
                                              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {p.name}
                  </Box>
                  {(() => {
                    const st = stateChip(p.state);
                    return (
                      <Chip
                        size="small"
                        label={st.label}
                        color={st.color}
                        variant={st.color === "default" ? "outlined" : "filled"}
                        title={st.title}
                        sx={{ ml: 1, flexShrink: 0 }}
                      />
                    );
                  })()}
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

      <SettingsCard
        icon={<FactCheckRoundedIcon />}
        title="Testdruck"
        description="Ein Blatt zur Kontrolle, bevor der erste Gast davorsteht."
      >
        <Stack spacing={2} alignItems="flex-start">
          <Typography variant="body2" color="text.secondary">
            Druckt eine Seite mit Rahmen, Eckwinkeln, Maßstab und Farbfeldern.
            Ist der Rahmen ringsum gleich breit und die Maßstab-Linie exakt so
            lang wie angeschrieben, stimmen Papierformat und Ränder — das sieht
            man einem Gruppenfoto nicht an.
          </Typography>
          <Button
            variant="outlined"
            startIcon={<PrintRoundedIcon />}
            disabled={!!testBlocked || testBusy}
            onClick={() => setTestOpen(true)}
          >
            {testBusy ? "Sende…" : "Testseite drucken"}
          </Button>
          {testBlocked && (
            <Typography variant="caption" color="text.secondary">
              {testBlocked}
            </Typography>
          )}
        </Stack>
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

      <Dialog
        open={testOpen}
        onClose={testBusy ? undefined : () => setTestOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <FactCheckRoundedIcon color="primary" />
          Testseite drucken?
        </DialogTitle>
        <DialogContent>
          {/* Der Hinweis auf das Blatt ist kein Beiwerk: Selphy-Papier kommt in
              gezaehlten Boegen, und die Kassette ist am Eventtag selten voll. */}
          <Typography variant="body2" color="text.secondary">
            Das verbraucht <strong>ein Blatt</strong> auf
            {" "}<strong>{st?.printer ?? "dem Standarddrucker"}</strong> — unabhängig
            davon, wie viele Kopien pro Druck eingestellt sind.
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            Gedruckt wird mit den gespeicherten Einstellungen, also genau so,
            wie die Box später ein Foto ausgibt.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button onClick={() => setTestOpen(false)} disabled={testBusy}
                  color="inherit" sx={{ flex: 1 }}>
            Abbrechen
          </Button>
          <Button variant="contained" disabled={testBusy} onClick={runTest} sx={{ flex: 1 }}>
            {testBusy ? "Sende…" : "Drucken"}
          </Button>
        </DialogActions>
      </Dialog>

      {toast && (
        <Alert severity={toast.sev} onClose={() => setToast(null)}>{toast.msg}</Alert>
      )}
    </Stack>
  );
}
