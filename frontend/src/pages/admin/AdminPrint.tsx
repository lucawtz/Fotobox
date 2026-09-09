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
  LinearProgress,
} from "@mui/material";
import PrintRoundedIcon from "@mui/icons-material/PrintRounded";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import FactCheckRoundedIcon from "@mui/icons-material/FactCheckRounded";
import StraightenRoundedIcon from "@mui/icons-material/StraightenRounded";
import Inventory2RoundedIcon from "@mui/icons-material/Inventory2Rounded";
import { api, AdminConfig, PaperState, Printer, PrinterInfo } from "../../api";
import SettingsCard from "./SettingsCard";

const MODES = [
  { value: "auto",  label: "Automatisch",
    hint: "Einzelfotos randlos, Collagen vollständig mit weißem Rand. Empfohlen." },
  { value: "cover", label: "Immer randlos",
    hint: "Füllt das Papier immer aus. Bei Collagen wird oben und unten abgeschnitten." },
  { value: "fit",   label: "Immer vollständig",
    hint: "Zeigt das ganze Bild, lässt dafür einen weißen Rand." },
];

// Muss zu gallery_server._BLEED_MAX_MM passen. Groessere Werte schneidet der
// Server ab, und ein Feld, dessen Eingabe stillschweigend anders gespeichert
// wird als sie dasteht, ist schlimmer als eins mit Grenze.
const BLEED_MAX_MM = 25;

/** Millimeter aus einem Eingabefeld. Nimmt auch das Komma an — auf einer
 *  deutschen Tastatur tippt niemand freiwillig einen Punkt in eine
 *  Millimeterangabe, und "2,5" als 0 zu lesen waere die schlechteste aller
 *  Antworten. Unlesbares wird 0, also "keine Korrektur". */
const parseMm = (v: string): number => {
  const n = Number(v.replace(",", ".").trim());
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(BLEED_MAX_MM, Math.round(n * 100) / 100));
};

// CUPS-Zustaende uebersetzen. printing._printer_states liefert das englische
// Wort aus `lpstat -p` durch (idle | printing | disabled) — in einer deutschen
// Oberflaeche stand da vorher schlicht "idle".
//
// Sonderfall "unknown": das heisst NICHT "Drucker kaputt", sondern "der Zustand
// war nicht auslesbar" — weder per IPP noch aus einem englischen lpstat (siehe
// printing.list_printers). Deshalb bleibt `ready` dort bewusst true; der
// gruene Erfolgs-Chip waere trotzdem falsch, denn zugesichert ist hier nichts.
// Neutral grau sagt das Richtige: unbekannt, wird aber angeboten.
type ChipColor = "success" | "warning" | "info" | "default";

const STATE_LABEL: Record<string, { label: string; color: ChipColor; title?: string }> = {
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

/** Der eine Chip, der in der Auswahlliste hinter dem Namen steht.
 *
 *  In eine Zeile passt genau eine Aussage, also die wichtigste. Der
 *  CUPS-Zustand ist dabei die schwaechste von allen: 'idle' heisst nur, dass
 *  die Warteschlange frei ist — ein ausgeschalteter Selphy meldet das auch.
 *  Deshalb kommt zuerst, was wirklich am Gerät haengt, und erst zuletzt der
 *  Zustand der Queue. */
const printerChip = (p: Printer): { label: string; color: ChipColor; title?: string } => {
  if (p.virtual)
    return { label: "kein Fotodrucker", color: "default" as const,
             title: "Von CUPS mitgelieferte Attrappe (Braille/PDF/Fax) — nimmt "
                  + "Auftraege an, wirft aber nie ein Foto aus." };
  if (p.connected === false)
    return { label: "nicht verbunden", color: "warning" as const,
             title: "Meldet sich nicht am USB — ausgeschaltet oder Kabel ab. "
                  + "CUPS wuerde den Drucker trotzdem als bereit fuehren." };
  const blocking = p.reasons.find((r) => r.blocking);
  if (blocking)
    return { label: blocking.text, color: "warning" as const,
             title: `Der Drucker meldet '${blocking.key}'. Solange das anliegt, `
                  + "bringt ein Druckversuch nichts." };
  const hint = p.reasons[0];
  if (hint)
    return { label: hint.text, color: "info" as const,
             title: `Der Drucker meldet '${hint.key}' — ein Hinweis, kein Hindernis.` };
  return stateChip(p.state);
};

// Muss zu paper.PACK_MAX passen.
const PACK_MAX = 999;

/** Ganze Blatt aus einem Eingabefeld, begrenzt wie der Server sie begrenzt.
 *  Unlesbares wird 0 — also "Zaehler aus" bzw. "leer". */
const parseSheets = (v: string): number => {
  const n = Math.round(Number(v.replace(",", ".").trim()));
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(PACK_MAX, n));
};

/** "vor 3 Tagen" statt eines Zeitstempels: die Frage vor dem Event ist nicht
 *  "wann genau", sondern "war das noch dieselbe Feier". */
const sinceLabel = (ts: number): string => {
  const days = Math.floor((Date.now() / 1000 - ts) / 86400);
  if (days <= 0) return "heute eingelegt";
  if (days === 1) return "gestern eingelegt";
  return `vor ${days} Tagen eingelegt`;
};

export default function AdminPrint() {
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [info, setInfo] = useState<PrinterInfo | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [printer, setPrinter] = useState("");
  const [copies, setCopies] = useState(1);
  const [mode, setMode] = useState("auto");
  // Die Millimeter bewusst als Text: waehrend man "2,5" tippt, ist der Wert
  // zwischendurch "2," — als Zahl gehalten haette das Feld den Rest verworfen.
  const [bleedLong, setBleedLong] = useState("0");
  const [bleedShort, setBleedShort] = useState("0");
  const [scale, setScale] = useState(100);
  // Papier bewusst als Text wie die Millimeter: waehrend man tippt, ist das
  // Feld zwischendurch leer, und als Zahl gehalten spraenge es auf 0.
  const [packSize, setPackSize] = useState("0");
  const [warnAt, setWarnAt] = useState("10");
  const [counted, setCounted] = useState("");
  const [paperBusy, setPaperBusy] = useState(false);
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
      setBleedLong(String(c.print_bleed_mm?.[0] ?? 0));
      setBleedShort(String(c.print_bleed_mm?.[1] ?? 0));
      setScale(c.print_scale_pct ?? 100);
      setPackSize(String(c.paper_pack_size ?? 0));
      setWarnAt(String(c.paper_warn_at ?? 10));
    });
    loadPrinters();
  }, []);

  const dirty = !!cfg && (
    enabled !== (cfg.print_enabled ?? true) ||
    printer !== (cfg.printer_name ?? "") ||
    copies !== (cfg.print_copies ?? 1) ||
    mode !== (cfg.print_mode ?? "auto") ||
    parseMm(bleedLong) !== (cfg.print_bleed_mm?.[0] ?? 0) ||
    parseMm(bleedShort) !== (cfg.print_bleed_mm?.[1] ?? 0) ||
    scale !== (cfg.print_scale_pct ?? 100) ||
    parseSheets(packSize) !== (cfg.paper_pack_size ?? 0) ||
    parseSheets(warnAt) !== (cfg.paper_warn_at ?? 10)
  );

  const save = async () => {
    setBusy(true);
    const bleed: [number, number] = [parseMm(bleedLong), parseMm(bleedShort)];
    const pack = parseSheets(packSize);
    const warn = parseSheets(warnAt);
    try {
      await api.admin.config.save({
        print_enabled: enabled,
        printer_name: printer,
        print_copies: copies,
        print_mode: mode as AdminConfig["print_mode"],
        print_bleed_mm: bleed,
        print_scale_pct: scale,
        paper_pack_size: pack,
        paper_warn_at: warn,
      });
      // Die Felder auf das zurueckschreiben, was gespeichert wurde: aus "2,5"
      // wird "2.5", aus "abc" eine 0. Sonst stuende im Feld etwas anderes als
      // im Drucker, und das Formular waere sofort wieder "geaendert".
      setBleedLong(String(bleed[0]));
      setBleedShort(String(bleed[1]));
      setPackSize(String(pack));
      setWarnAt(String(warn));
      setCfg({ ...cfg!, print_enabled: enabled, printer_name: printer,
               print_copies: copies, print_mode: mode as AdminConfig["print_mode"],
               print_bleed_mm: bleed, print_scale_pct: scale,
               paper_pack_size: pack, paper_warn_at: warn });
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

  /** Neues Paket eingelegt bzw. nachgezaehlt. Beide Wege liefern den neuen
   *  Stand direkt zurueck — kein zweiter Ladelauf, damit die Zahl nicht kurz
   *  auf dem alten Wert stehen bleibt. */
  const paperAction = async (fn: () => ReturnType<typeof api.admin.paperRefill>,
                             okMsg: string) => {
    setPaperBusy(true);
    try {
      const r = await fn();
      if (r.ok) {
        setInfo((prev) => (prev ? { ...prev, paper: r.paper } : prev));
        setCounted("");
        setToast({ sev: "success", msg: okMsg });
      } else {
        setToast({ sev: "error", msg: r.error ?? "Papierzähler nicht geändert" });
      }
    } catch (e) {
      setToast({ sev: "error", msg: e instanceof Error ? e.message : String(e) });
    } finally { setPaperBusy(false); }
  };

  const st = info?.status;
  const paper: PaperState | undefined = info?.paper;
  // Was das Geraet selbst meldet, getrennt nach Gewicht: "Papier leer"
  // haelt den Druck auf, "Farbband fast leer" ist nur ein Hinweis und darf
  // nicht wie ein Fehler aussehen.
  const reasons = st?.reasons ?? [];
  const blockingReasons = reasons.filter((r) => r.blocking);
  const hintReasons = reasons.filter((r) => !r.blocking);

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
      ) : st?.connected === false ? (
        // Der haeufigste Fall am Event-Tag und der einzige, den CUPS gar nicht
        // sieht: Drucker aus. Die Warteschlange meldet weiter 'idle', hier
        // stand deshalb frueher ein gruenes "ist bereit".
        <Alert severity="warning">
          Drucker <strong>{st.printer}</strong> meldet sich nicht am USB — er ist
          ausgeschaltet oder das Kabel ist ab. Die Box blendet den
          „Drucken"-Knopf aus, bis er wieder da ist.
        </Alert>
      ) : blockingReasons.length > 0 ? (
        <Alert severity="warning">
          Drucker <strong>{st?.printer}</strong> meldet:{" "}
          <strong>{blockingReasons.map((r) => r.text).join(", ")}</strong>.
          Solange das anliegt, bringt ein Druckversuch nichts — die Box blendet
          den „Drucken"-Knopf aus.
        </Alert>
      ) : st?.available && st.state === "unknown" ? (
        // Angeboten, aber nicht bestaetigt: gruen waere hier zu viel
        // versprochen — weder IPP noch lpstat haben den Zustand preisgegeben.
        <Alert severity="info">
          Drucker <strong>{st.printer}</strong> ist eingerichtet, sein Zustand
          lässt sich aber nicht auslesen. Der „Drucken"-Knopf wird angezeigt —
          ob wirklich Papier kommt, zeigt erst der erste Druckversuch.
        </Alert>
      ) : st?.available ? (
        <Alert severity="success">
          Drucker <strong>{st.printer}</strong> ist bereit. Der „Drucken"-Knopf
          wird auf dem Boxschirm angezeigt.
          {hintReasons.length > 0 && (
            <>
              {" "}Das Gerät meldet dazu:{" "}
              <strong>{hintReasons.map((r) => r.text).join(", ")}</strong>.
            </>
          )}
        </Alert>
      ) : (
        <Alert severity="warning">
          {st?.message ?? "Drucksystem nicht erreichbar"}. Solange kein Drucker
          bereit ist, blendet die Box den „Drucken"-Knopf aus — ein Knopf, der
          nichts tut, verwirrt Gäste mehr, als dass er hilft.
        </Alert>
      )}

      {/* Zweite Zeile neben dem Druckerzustand, nicht statt ihm: der Drucker
          kann bereit sein und das Papier trotzdem gleich alle. Nur wenn eine
          Paketgroesse hinterlegt ist — sonst ist die Zahl geraten. */}
      {paper?.tracked && paper.low && (
        <Alert severity={paper.empty ? "warning" : "info"}>
          {paper.empty ? (
            <>
              Rechnerisch ist das Paket <strong>durch</strong> — seit dem
              Einlegen wurden {paper.used} von {paper.size} Blatt gedruckt.
              Nachlegen und unten auf „Neues Paket eingelegt" tippen.
            </>
          ) : (
            <>
              Noch etwa <strong>{paper.left} Blatt</strong> im Drucker. Jetzt
              ein Paket bereitlegen — der Selphy meldet leeres Papier erst,
              wenn das letzte Blatt durch ist.
            </>
          )}
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
                    const st = printerChip(p);
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
        icon={<StraightenRoundedIcon />}
        title="Randlos-Überstand"
        description="Wenn das Bild über die Blattkante oder die Abreisslaschen läuft."
      >
        {cfg ? (
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Randlos heißt beim Treiber: er rechnet auf eine Fläche, die grösser
              ist als das Papier, und schiebt das fertige Bild damit über die
              Kante. <strong>Messen mit dem Testdruck:</strong> dessen Rahmen
              liegt 5&nbsp;mm vom Blattrand. Kommt er auf einer Achse mit nur
              3&nbsp;mm heraus, sind hier für diese Achse 2&nbsp;mm einzutragen.
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Lange Kante (mm)"
                value={bleedLong}
                onChange={(e) => setBleedLong(e.target.value)}
                disabled={!enabled}
                sx={{ maxWidth: { sm: 220 } }}
                inputProps={{ inputMode: "decimal" }}
                helperText="Links und rechts — beim Selphy die Laschenseiten"
              />
              <TextField
                label="Kurze Kante (mm)"
                value={bleedShort}
                onChange={(e) => setBleedShort(e.target.value)}
                disabled={!enabled}
                sx={{ maxWidth: { sm: 220 } }}
                inputProps={{ inputMode: "decimal" }}
                helperText="Oben und unten — die echte Blattkante"
              />
            </Stack>
            <TextField
              type="number"
              label="Skalierung (%)"
              value={scale}
              onChange={(e) =>
                setScale(Math.max(50, Math.min(100, Number(e.target.value) || 100)))}
              disabled={!enabled}
              inputProps={{ min: 50, max: 100 }}
              sx={{ maxWidth: 200 }}
              helperText="Grobe Korrektur über beide Achsen zugleich. 100 = aus."
            />
            {/* Beide Schrauben wirken nacheinander — die Millimeter in der
                Bildaufbereitung, die Prozent erst im Treiber. Wer an beiden
                dreht, korrigiert doppelt und wundert sich über den weissen
                Rand oben und unten. */}
            {scale !== 100 && (parseMm(bleedLong) > 0 || parseMm(bleedShort) > 0) && (
              <Alert severity="warning">
                Millimeter und Skalierung sind beide aktiv und ziehen das Bild
                nacheinander zusammen. Für eine saubere Einstellung die
                Skalierung auf <strong>100</strong> setzen und nur mit den
                Millimetern arbeiten — die wirken je Achse einzeln.
              </Alert>
            )}
          </Stack>
        ) : <Skeleton variant="rounded" height={56} />}
      </SettingsCard>

      <SettingsCard
        icon={<Inventory2RoundedIcon />}
        title="Papiervorrat"
        description="Mitgezählt, weil der Drucker es nicht sagt."
      >
        {info === null ? <Skeleton variant="rounded" height={120} /> : (
          <Stack spacing={2.5}>
            {paper?.tracked ? (
              <Box>
                <Stack direction="row" alignItems="baseline" spacing={1}>
                  <Typography variant="h4" sx={{ fontWeight: 500 }}>
                    {paper.empty ? "0" : `ca. ${paper.left}`}
                  </Typography>
                  <Typography variant="body1" color="text.secondary">
                    von {paper.size} Blatt
                  </Typography>
                </Stack>
                <LinearProgress
                  variant="determinate"
                  value={Math.max(0, Math.min(100, (paper.left / paper.size) * 100))}
                  color={paper.empty ? "error" : paper.low ? "warning" : "primary"}
                  sx={{ mt: 1.5, height: 8, borderRadius: 4 }}
                />
                <Typography variant="caption" color="text.secondary"
                            sx={{ display: "block", mt: 1 }}>
                  {paper.used} gedruckt
                  {paper.loaded_at
                    ? ` · ${sinceLabel(paper.loaded_at)}`
                    : " · noch nie zurückgesetzt — nach dem nächsten Nachlegen "
                      + "stimmt der Stand"}
                  {" · "}Warnung ab {paper.warn_at} Blatt
                </Typography>
              </Box>
            ) : (
              <Alert severity="info" variant="outlined">
                Der Zähler ist aus. Blattzahl des eingelegten Pakets eintragen
                und speichern, dann zählt die Box jeden Druck mit. Canon-Pakete:
                KP-108IN und RP-108 = 108 Blatt, KP-72IN = 72, KP-36IP = 36.
              </Alert>
            )}

            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Blatt je Paket"
                value={packSize}
                onChange={(e) => setPackSize(e.target.value)}
                sx={{ maxWidth: { sm: 220 } }}
                inputProps={{ inputMode: "numeric" }}
                helperText="0 = Zähler aus"
              />
              <TextField
                label="Warnen ab (Blatt)"
                value={warnAt}
                onChange={(e) => setWarnAt(e.target.value)}
                sx={{ maxWidth: { sm: 220 } }}
                inputProps={{ inputMode: "numeric" }}
                helperText="10 ≈ zehn Minuten Druckzeit"
              />
            </Stack>

            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}
                   alignItems={{ sm: "flex-start" }}>
              <Button
                variant="outlined"
                disabled={paperBusy || dirty}
                onClick={() => paperAction(api.admin.paperRefill,
                                           "Zähler zurückgesetzt — Paket ist voll")}
              >
                Neues Paket eingelegt
              </Button>
              <Stack direction="row" spacing={1} alignItems="flex-start">
                <TextField
                  label="Nachgezählt"
                  value={counted}
                  onChange={(e) => setCounted(e.target.value)}
                  disabled={!paper?.tracked}
                  sx={{ width: 150 }}
                  inputProps={{ inputMode: "numeric" }}
                  helperText="Blatt, die wirklich drin liegen"
                />
                <Button
                  sx={{ mt: 1 }}
                  disabled={paperBusy || dirty || !paper?.tracked || counted.trim() === ""}
                  onClick={() => paperAction(
                    () => api.admin.paperSetLeft(parseSheets(counted)),
                    `Stand gesetzt: noch ${parseSheets(counted)} Blatt`)}
                >
                  Übernehmen
                </Button>
              </Stack>
            </Stack>
            {dirty && (
              <Typography variant="caption" color="text.secondary">
                Erst speichern — der Zähler rechnet mit der gespeicherten
                Paketgröße, nicht mit der im Formular.
              </Typography>
            )}

            {/* Der Zaehler ist eine Schaetzung. Das gehoert dahin, wo die Zahl
                steht, nicht in eine Fussnote: wer ihm blind glaubt, steht mit
                leerer Kassette da. */}
            <Typography variant="body2" color="text.secondary">
              Gezählt wird jeder Druckauftrag, den der Drucker annimmt —
              Testdrucke und mehrere Kopien eingeschlossen. Ein Papierstau oder
              ein abgebrochener Auftrag geht daneben, deshalb steht überall
              „ca.". Nach dem Nachzählen den Stand hier geradeziehen. Gesperrt
              wird nichts: ob wirklich Papier da ist, meldet allein der Drucker.
            </Typography>
          </Stack>
        )}
      </SettingsCard>

      <SettingsCard
        icon={<FactCheckRoundedIcon />}
        title="Testdruck"
        description="Ein Blatt zur Kontrolle, bevor der erste Gast davorsteht."
      >
        <Stack spacing={2} alignItems="flex-start">
          <Typography variant="body2" color="text.secondary">
            Druckt eine Seite mit Rahmen, Eckwinkeln, Maßstab und Farbfeldern.
            Der Rahmen liegt 5&nbsp;mm vom Blattrand: ist er ringsum gleich breit
            und die Maßstab-Linie exakt so lang wie angeschrieben, stimmen
            Papierformat und Ränder — das sieht man einem Gruppenfoto nicht an.
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
            setBleedLong(String(cfg.print_bleed_mm?.[0] ?? 0));
            setBleedShort(String(cfg.print_bleed_mm?.[1] ?? 0));
            setScale(cfg.print_scale_pct ?? 100);
            setPackSize(String(cfg.paper_pack_size ?? 0));
            setWarnAt(String(cfg.paper_warn_at ?? 10));
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
