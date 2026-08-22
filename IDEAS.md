# Fotobox — Ideenliste (unbewertet)

Sammelbecken für alles, was die Box *könnte*. Nichts hier ist beschlossen,
nichts hier hat einen Termin, und nichts hier gefährdet das Event.

**Abgrenzung zur `ROADMAP.md`:** Die Roadmap ist verbindlich und hängt am
Event-Termin — jeder Punkt dort ist entschieden, verortet (`Datei:Zeile`) und
begründet. Hier steht das Gegenteil: Halbgares, Unentschiedenes, Sachen mit
offenen Fragen. Die Trennung ist Absicht. Rohe Wünsche in P3 zu kippen würde
die Roadmap unbrauchbar machen — dort soll man ablesen können, was zu tun ist,
nicht was jemand mal schön fände.

**Übergang:** Eine Idee wandert erst dann in die Roadmap (frühestens P3), wenn
sie entschieden ist *und* die drei Angaben trägt: **was**, **wo**, **warum**.
Bis dahin bleibt sie hier.

**Pflege:** Verworfene Ideen werden nicht gelöscht, sondern mit `~~Titel~~` und
einer Zeile Grund markiert — sonst kommen sie in einem halben Jahr wieder.

---

## Aufnahme & Collage

- **Collage-Stil auswählbar machen** — *Bedienung entschieden 22.08.2026*
  *Heute:* `collage.py:make_collage` baut ausnahmslos ein 2×2-Raster — vier
  Bilder auf gleiche Größe skaliert, 20 px weißer Steg (`_GAP`, `_BG`),
  JPEG 92. Die Anzahl steht als `COLLAGE_SHOTS = 4` in `main.py:88`, und ob
  Einzelfoto oder Collage entsteht, entscheidet allein, welcher Knopf gedrückt
  wurde (`main.py:369`).
  *Denkbare Stile:* 2×2 (wie heute) · Fotostreifen 4×1 hochkant · ein großes
  Bild plus drei kleine · 3er-Streifen.
  **Entschieden: Der Gastgeber wählt den Stil im Admin-Panel, der Gast wählt
  nicht.** Damit bleibt die Bedienung an der Box unverändert zweiknöpfig — kein
  dritter Taster, kein Auswahlbildschirm vor jedem Foto. Der Stil ist eine
  Eigenschaft des Abends, keine des einzelnen Gastes; das passt zum Rest des
  Panels, in dem der Gastgeber ohnehin Eventname, Untertitel und Countdown für
  den Abend festlegt.
  *Wo das konkret landet:* ein Feld `collage_style` in `config._MIETER_FIELDS`
  (`config.py:16-26` — mieterspezifisch, gehört in die lokale `config.json`)
  und in `config.HANDOVER_FIELDS` (`config.py:74`), damit „Box vorbereiten" es
  für den nächsten Gastgeber zurücksetzt. Bedienelement in
  `frontend/src/pages/admin/AdminEvent.tsx`, direkt neben dem Countdown-Regler.
  `make_collage` bekommt den Stil als Parameter, `main.py` reicht ihn aus der
  Config durch.
  *Offen bleibt:*
  (1) **Welche Stile überhaupt** — die Liste oben ist Brainstorming, nicht
  entschieden.
  (2) **Papier.** Ein Fotostreifen passt nicht ohne Schnitt auf Selphy 10×15;
  entweder Streifen mit Rand auf 10×15 drucken oder das Format aufgeben.
  (3) **Aufnahmezahl.** `COLLAGE_SHOTS` ist heute fest an das 2×2 gekoppelt.
  Sobald ein Stil eine andere Zahl braucht, muss die Zahl aus dem Stil folgen
  und darf nicht zweite, unabhängige Einstellung werden — sonst sind
  Stil und Anzahl irgendwann widersprüchlich eingestellt.

- **Vorlagen-Layer (Rahmen, Eventname, Logo aufs Bild)**
  *Heute:* Was aus dem Drucker kommt, ist ein nacktes Foto — Branding gibt es
  nur auf dem Boxschirm und in der Galerie. Ein PNG mit Alphakanal, das
  `make_collage` zum Schluss über die Leinwand legt, wäre der kleinste denkbare
  Einstieg: Vorlagen als Dateien in `Layout/`, Auswahl über die Config.
  *Warum interessant:* Es ist der einzige Punkt dieser Liste, den der Gast mit
  nach Hause nimmt. Hängt eng am Stil-Punkt darüber — Stil und Vorlage sind
  dieselbe Entscheidung, einmal geometrisch und einmal grafisch.

- **Anzahl der Aufnahmen konfigurierbar** (3 / 4 / 6 statt fest 4)
  Klein, solange das Raster mitzieht — `COLLAGE_SHOTS` ist heute an das
  2×2-Layout gekoppelt und darf nicht allein verstellt werden.

- **„Nochmal?" nach der Aufnahme**
  Heute landet jeder Auslöser sofort und endgültig in der Galerie. Eine
  Verwerfen-Möglichkeit direkt nach der Collage würde Fehlaufnahmen abfangen —
  kostet aber wieder einen Bedienschritt und eine Zeitschranke (wer nicht
  reagiert, bekommt das Foto behalten).

- **Filter (S/W, Sepia)** — passend zum warmen Theme; Pillow kann das ohne
  weitere Abhängigkeit. Gleiche offene Frage wie beim Stil: Wer wählt, und wann.

## Box-Oberfläche

- **Eigenes Hintergrundbild für die Box-UI**
  *Heute:* Der Hintergrund ist ein vertikaler Verlauf `bg_top → bg_bottom`,
  einmal pro Theme-Änderung gebaut (`ui._build_gradient_bg`, `ui.py:873`).
  Der Gastgeber kann im Admin-Panel 16 Theme-Farben einzeln stellen, hat acht
  Presets (`frontend/src/pages/admin/themePresets.ts`) und eine Live-Vorschau —
  aber kein eigenes Bild.
  *Wichtig, sonst dreht man einen Kreis:* **Genau das gab es schon einmal und
  wurde bewusst abgeschafft.** `b0b11ef` band `Overlay-Fotobox.jpg` als
  Hintergrund ein, `43ee442` ersetzte es durch das Theme-System — mit der
  Begründung, der Mieter solle Farben ändern können, „ohne ein neues PNG zu
  erstellen". Der Grund gilt weiter.
  *Was sich unterscheiden müsste:* Das alte Overlay hat das **ganze Layout**
  bestimmt — die Polaroid- und Live-View-Koordinaten stammten aus einer
  Schwarzbereich-Erkennung im PNG. Ein Hintergrundbild neuer Art wäre
  ausschließlich die unterste Ebene: Es ersetzt den Verlauf, alles darüber
  bleibt gezeichnet. Sidebar, Polaroids, Live-Rahmen rühren es nicht an. Nur so
  bleibt das Bild optional und der Theme-Weg für alle, die keine Grafik
  mitbringen, intakt.
  *Was schon da ist:* Der Upload-Weg existiert — `POST /api/admin/logo`
  (`gallery_server.py:1509`) nimmt eine Datei an und prüft sie über
  `PIL.Image.verify()`. Ein zweiter Endpunkt für den Hintergrund wäre derselbe
  Code. Als Mieter-Asset müsste „Box vorbereiten" ihn löschen, genau wie das
  Logo (`config.HANDOVER_FIELDS`, Rückfall auf den Verlauf).
  *Offen bleibt:*
  (1) **Lesbarkeit.** Über einem unruhigen Foto verschwinden Polaroids und
  Text. Stellschrauben wären der vorhandene `panel_alpha` und ein
  abdunkelnder Schleier über dem Bild — beides eher Pflicht als Option.
  (2) **Zuschnitt.** `W, H = 1920, 1080` steht fest verdrahtet in `ui.py:16`;
  ein Bild braucht eine Cover-Skalierung. Hängt am P3-Punkt
  „Auflösungsunabhängiges pygame-Layout" der Roadmap.
  (3) **Wer liefert das Bild?** Ohne Vorlage im richtigen Seitenverhältnis
  landet man wieder bei „Gastgeber muss Grafiker sein" — dem Problem, das
  `43ee442` gerade beseitigt hat.

- **Mehr Gestaltungsspielraum allgemein**
  Denkbare weitere Stellschrauben: Schriftart wählbar · Sidebar links oder
  rechts · Polaroid-Rahmen an/aus · eigene Button-Labels (`config.py:127`
  kennt bereits `actions[]`, aber nur als Owner-Default — der Gastgeber kommt
  nicht dran) · Gestaltung des Idle-Screens und der Slideshow.
  *Gegenargument, das mitgeschrieben gehört:* Jeder zusätzliche Regler ist
  eine Kombination mehr, die nie jemand durchprobiert — und die erste, die am
  Eventabend unlesbar aussieht, fällt auf die Box zurück. Der stärkere Hebel
  sind **mehr und bessere Presets** (heute acht) plus die Live-Vorschau, nicht
  mehr Einzelregler. Wenn Einzelregler, dann hinter einem „Erweitert"-Bereich.

## Gäste

- **Mehrsprachigkeit**
  *Heute:* Alles ist fest auf Deutsch — die pygame-Texte in `ui.py`, das
  Captive-Portal-HTML in `gallery_server.py` und die React-Oberflächen unter
  `frontend/src`. Kein `i18n`, keine Sprachdateien, die Strings stehen als
  Literale im Code. Bei internationalen Gästen — auf Hochzeiten eher Regel als
  Ausnahme — steht vor der Box jemand, der „Drück einen Knopf" nicht liest.
  *Warum es mehr Arbeit ist, als es klingt:* Es sind **drei** Oberflächen in
  zwei Sprachen und zwei Frameworks. Deutsch/Englisch in allen dreien einzeln
  zu pflegen ist genau das Doppelpflege-Problem, das der Roadmap-Punkt „Box-UI
  als App bauen" (P3) für Theme und Branding schon beschreibt. Wenn die
  Web-Oberfläche jemals kommt, wird Mehrsprachigkeit dort einmal gelöst statt
  dreimal — **also besser danach als davor.**
  *Offen bleibt:*
  (1) **Wer stellt um?** Eine Flagge zum Antippen bricht das Zwei-Knopf-Konzept
  der Box. Wahrscheinlicher wieder: der Gastgeber legt die Sprache im
  Admin-Panel für den Abend fest — dieselbe Entscheidung wie beim Collage-Stil.
  Zweisprachig gleichzeitig anzuzeigen ist die Alternative, kostet aber Platz,
  den das 1920×1080-Layout nicht übrig hat.
  (2) **Wie weit?** Nur die vier, fünf Sätze, die der Gast an der Box sieht,
  ist ein Nachmittag. Galerie und Admin-Panel mit dazu ist ein Vielfaches —
  und das Admin-Panel sieht ohnehin nur der Gastgeber, der Deutsch kann.
  Der ehrliche Zuschnitt ist vermutlich: **Box-UI und Galerie ja, Admin nein.**

- **Nachdruck aus der Galerie** — heute druckt nur die Box selbst. Ein
  Druckknopf am Foto in der Galerie bräuchte eine Freigabe (sonst leert der
  erste Spaßvogel die Farbbandkassette) und eine sichtbare Warteschlange.
- **Download des eigenen Fotos in Originalgröße** — die Galerie liefert heute
  `/img`, `/thumb`, `/preview`; ob ein Handy im Hotspot daraus einen sauberen
  Download macht, ist ungeprüft.
- **Bewegtbild (GIF / Boomerang)** — reizvoll, aber gphoto2 liefert Einzelbilder;
  die Serienaufnahme müsste über die Capture-Card laufen, deren Bild deutlich
  schlechter ist als das der Kamera. Vermutlich mehr Aufwand als Ertrag.

## Betrieb

- **Papierzähler und Druckkontingent**
  *Heute:* Nichts zählt mit. `printing.refresh_status` fragt CUPS nur nach dem
  Zustand (`idle` / `printing` / `disabled`, `printing.py:61-77`) — einen
  Füllstand liefert das nicht, und der Selphy meldet über USB auch keinen.
  Das Ende der Kassette merkst du am Eventabend also genau dann, wenn es
  eintritt.
  *Denkbar:* Kassettengröße in die Config, ein Zähler, den `print_photo`
  hochzählt, Restanzeige im Admin-Panel und eine Warnung ab einer Schwelle.
  Zurückgesetzt wird beim Kassettenwechsel per Knopf im Panel.
  *Der Haken, der das Feature prägt:* `print_photo` gibt `True` zurück, sobald
  **CUPS den Job angenommen hat** — nicht wenn das Blatt gedruckt ist; der
  Docstring sagt das ausdrücklich (`printing.py:308-313`). Ein Zähler zählt
  also angenommene Aufträge, keine Blätter. Papierstau, abgebrochener Job oder
  ein Neustart mit Jobs in der Warteschlange lassen ihn driften. Daraus folgt:
  **Die Zahl ist eine Schätzung und muss im Panel von Hand korrigierbar sein**
  — sonst ist sie schlimmer als keine Zahl, weil man sich auf sie verlässt.
  Ein Zähler, der „37 übrig" behauptet, während die Kassette leer ist, hilft
  niemandem.
  *Nicht vergessen:* `print_copies` erlaubt bis zu 9 Kopien pro Auftrag
  (`printing.py:294-296`), der Zähler muss also die Kopienzahl addieren, nicht
  eins. Und wenn der Gästebuch-Doppeldruck je kommt, verdoppelt sich der
  Verbrauch pro Aufnahme — beide Punkte hängen zusammen.
  *Offene Frage:* Soll ein erreichtes Kontingent das Drucken **sperren** oder
  nur warnen? Sperren schützt den Vorrat für den späteren Abend, nimmt dem
  Gastgeber aber die Entscheidung aus der Hand. Warnen ist der sanftere
  Anfang.

- **Abendbilanz** — Fotos gesamt, Drucke, Spitzenzeit, längste Pause. Die Daten
  liegen ohnehin im Event-Ordner und in den Logs; nützlich für die Frage, wie
  viel Papier beim nächsten Mal mitmuss.
