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

- **Greenscreen: Hintergrund gegen eine Vorlage tauschen**
  *Die Idee:* Grüner Stoff hinter der Box, beim Auslösen ersetzt die Software
  das Grün durch ein Motiv — Strand, Skyline, Eventgrafik. Der Gast nimmt ein
  Bild mit, das nicht nach „Fotobox in einer Turnhalle" aussieht.
  *Was schon da ist:* `opencv-python` und `numpy` stehen bereits in
  `requirements.txt` (heute für den QR-Zuschnitt in `ui._crop_to_code`) — das
  Keying selbst zieht also keine neue Abhängigkeit: nach HSV wandeln, Maske
  über einen Farbbereich, Ränder weichzeichnen, per Maske komponieren. Die
  Motive lägen als Dateien in `Layout/`, wo heute schon `logo.png` und die
  beiden QR-Codes liegen.
  *Wo es in den Ablauf gehört:* Direkt hinter `camera.capture` (`camera.py:200`)
  und **vor** `collage.make_collage` (`collage.py:86`) — auf jede Einzelaufnahme,
  nicht auf das fertige 2×2. Sonst müsste das Motiv über den weißen Steg
  hinweg passen. Nebeneffekt und richtig so: die vier `collage_<gid>_n.jpg` in
  der Galerie sind dann ebenfalls freigestellt.
  *Der ehrliche Haken — es ist ein Licht-Problem, kein Code-Problem:*
  Chroma-Key steht und fällt mit gleichmäßig ausgeleuchtetem, faltenfreiem
  Grün. Falten, ein Schlagschatten vom Gast, ein Fenster mit Tageslicht
  daneben — und die Maske frisst Löcher oder lässt grüne Säume stehen. Dazu
  verschwindet alles Grüne am Gast gleich mit (Kleid, Brille, Deko). Der
  Aufwand liegt also im **Aufbau** — Stoff mit Rahmen plus mindestens zwei
  Lampen, mehr Platz, längeres Einrichten beim Mieter — und der wandert in den
  Mietvorgang, nicht in den Code. Das ist die Entscheidung, nicht die
  Implementierung.
  *Rechenzeit, messen bevor gebaut wird:* Die 700D liefert volle Auflösung;
  vier solche Bilder zu keyen kostet auf dem Pi genau dort Zeit, wo der Gast
  vor dem Result-Screen wartet. `printing.py:266-271` skaliert für den Druck
  ohnehin erst auf 10×15 bei `print_dpi` herunter — dort zu keyen wäre um ein
  Vielfaches billiger, betrifft aber nur den Ausdruck und nicht das Bild in der
  Galerie. Erst messen, dann entscheiden.
  *Live-Vorschau wäre der billigste Teil, aber ein eigenes Thema:*
  `ui._draw_live` (`ui.py:696`) hat den Frame bereits als numpy-Array, schneidet
  ihn zu und skaliert ihn auf `live_view_rect` (`config.py:134`, 800×450)
  herunter — eine Maske auf diesem kleinen Frame ist in der 30-fps-Schleife
  (`main.py:465`) vermutlich unproblematisch. Nur: Vorschau und Foto sind
  **zwei verschiedene Kameras** — die Vorschau kommt von der HDMI-Capture-Card,
  das Foto von der 700D. Weißabgleich und Ausschnitt unterscheiden sich, die
  Vorschau zeigt also nicht, was hinterher gedruckt wird. Entweder man
  akzeptiert sie als grobe Anzeige „so ungefähr wirst du am Strand stehen" —
  oder man lässt sie unangetastet und überrascht den Gast im Result-Screen.
  *Die Variante ohne Stoff:* Personensegmentierung per Modell (MediaPipe,
  `rembg`) braucht keinen Greenscreen, dafür ein Modell auf dem Pi, deutlich
  mehr Rechenzeit pro Bild und liefert bei Gruppen und ausgestreckten Armen
  ausgefranste Kanten. Reizvoll, weil der ganze Aufbau-Haken entfällt — aber
  eine andere Baustelle als der Zehnzeiler mit `cv2.inRange`, und keine, die
  man nebenbei aufmacht.
  *Offen bleibt:*
  (1) **Wer wählt das Motiv?** Dieselbe Frage wie beim Collage-Stil. Der
  Gastgeber im Admin-Panel wäre konsistent und ließe die Zwei-Knopf-Bedienung
  intakt — nur ist beim Hintergrund die Auswahl durch den Gast gerade der Reiz,
  und der kostet genau den Auswahlbildschirm, den der Stil-Punkt bewusst
  abgelehnt hat. Kompromiss wäre: Der Gastgeber schaltet drei Motive frei,
  die Box rotiert sie.
  (2) **Aus heißt aus.** Hängt kein Stoff, muss das Feature vollständig
  abschaltbar sein und darf nicht halb greifen — eine Maske, die im
  Wohnzimmerhintergrund zufällig Grüntöne findet, ruiniert jedes Foto.
  (3) **Gemeinsame Sache mit dem Vorlagen-Layer** weiter oben: Hintergrund
  (unterste Ebene) und Rahmen (oberste Ebene) sind zwei Ebenen desselben
  Bildes. Sie sollten aus demselben Ordner und derselben Auswahl kommen, sonst
  pflegt man zwei Vorlagensysteme nebeneinander.
  (4) **Toleranz-Regler.** Farbbereich und Kantenweichheit müssen am
  Eventabend nachstellbar sein, sonst steht man vor einem Stoff, den der fest
  verdrahtete Grünbereich nicht trifft. Gehört ins Admin-Panel mit
  Live-Vorschau — ohne die ist so ein Regler unbedienbar.

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

- **Ton: Countdown-Piep und Auslösegeräusch**
  *Heute:* Die Box ist stumm. Im ganzen Projekt steht kein einziger
  `pygame.mixer`-Aufruf — der Countdown existiert nur auf dem Bildschirm.
  *Warum das am Eventabend zählt:* Der Gast schaut in die Kamera, nicht auf
  den Monitor — also genau dann nicht hin, wenn der Countdown läuft. Ein Tick
  pro Sekunde und ein Auslösegeräusch sagen ihm ohne Blickwechsel, wann er
  lächeln muss und dass das Bild im Kasten ist. Von allen Punkten dieser Liste
  ist das vermutlich der beste Wirkung-pro-Zeile.
  *Wie klein das wäre:* `pygame.init()` (`ui.py:415`) startet den Mixer
  ohnehin mit. Es fehlen eine Handvoll kurzer Dateien und ein `play()` an drei
  Stellen — Countdown-Tick, Auslöser, Fehlermeldung. Keine neue Abhängigkeit.
  *Offen bleibt:*
  (1) **Woher kommt der Ton überhaupt?** Der Pi hängt am HDMI-Monitor; ob der
  Lautsprecher hat und ob der in einer lauten Feier durchdringt, ist ungeprüft.
  Wahrscheinlich braucht es einen kleinen Aktivlautsprecher — dann ist es auch
  ein Punkt auf der Packliste, nicht nur Software.
  (2) **Lautstärke ins Panel, mit „aus" als echter Stellung.** Steht die Box
  während der Trauung im Nebenraum, will niemand einen piependen Kasten.
  (3) **Sauber ausfallen.** Findet SDL kein Audiogerät, darf das die Box nicht
  anhalten — `pygame.init()` meldet so etwas nicht laut, ein fehlender Sound
  muss stillschweigend übersprungen werden.
  (4) **Welcher Ton.** Kamera-Klack oder dezenter Ton ist Geschmack — aber
  einmal falsch gewählt, hört man ihn den ganzen Abend.

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

- **QR direkt auf das eben aufgenommene Foto**
  *Heute:* Der Result-Screen zeigt zehn Sekunden lang das fertige Bild und
  oben rechts einen QR-Code — aber `_draw_qr_result` (`ui.py:1408`) blittet
  dieselbe Surface wie die Sidebar (`self._qr_surf`, erzeugt aus
  `gallery_url`). Der Code führt also in die Galerie, nicht auf das Foto. Wer
  sein Bild will, sucht es dort selbst.
  *Was schon da ist:* Die Deep-Link-Route existiert —
  `/photo/:event/:filename` (`frontend/src/App.tsx:24`), inklusive
  SPA-Fallback (Roadmap P0-2). `_make_qr` (`ui.py:2571`) erzeugt Codes in
  Theme-Farben mit Kontrastprüfung, und Event-Ordner wie Dateiname kennt
  `main.py` im Moment des Result-Screens ohnehin.
  *Der Haken, an dem die Idee hängt — die Modulzahl:* Der Galerie-Code trägt
  `http://192.168.4.1/`, das sind 33 Module und bei 132 px Kachel 4 px pro
  Modul. Der Kommentar an `QR_SIZE` (`ui.py:2459-2472`) hält den gemessenen
  Preis fest: im Decodertest mit Verkleinerung und Unschärfe reicht das für
  1 von 6 Stufen, bei 231 px wären es 4 von 6. **Die Größe ist eine bewusste
  Gestaltungsentscheidung und kein Fehler, der „korrigiert" werden will.**
  Eine Foto-URL ist aber ein Vielfaches länger —
  `/photo/2026-10-17_hochzeit-anna-und-tim/collage_1760000000000.jpg` sind über
  sechzig Zeichen. Das hebt den Code um mehrere Versionen und drückt die
  Modulbreite bei gleicher Kachel unter das, was ein Handy aus einem Meter
  Entfernung noch liest. **Ohne Kurz-Link wird das nichts.**
  *Also: Kurz-Link zuerst.* Etwas wie `/f/<code>` mit vier, fünf Zeichen. Die
  Mechanik dafür steht schon in `/go/<slug>` (`gallery_server.py:706`), wo ein
  kurzer Slug auf eine lange Ziel-URL zeigt — inklusive der Lehre, nur echte
  http(s)-Ziele durchzulassen.
  *Offen bleibt:*
  (1) **Die zehn Sekunden.** Der Result-Screen läuft nach 10 s ab
  (`main.py:416`). Handy zücken, entsperren, scannen, laden — das ist knapp.
  Entweder die Zeit hochsetzen (dann wartet die Schlange) oder den Code
  zusätzlich am Foto in der Polaroid-Wand anbieten.
  (2) **Lesbarkeit über dem Bild.** Der Code sitzt auf dem Foto
  (`ui.py:1413`) und bringt seine Cremekarte mit — geprüft ist das aber nur
  für die ruhige Sidebar, nicht über einem hellen Brautkleid.
  (3) **Lebensdauer.** `disk_monitor` räumt nach `photo_max_age_days` (7) und
  ab `max_photos` (500) auf (`config.py:82,165`). Wer den Code am nächsten
  Wochenende scannt, landet im Leeren — die Seite muss das erklären, statt
  wortlos auf die Startseite zu werfen.

- **Nachdruck aus der Galerie** — heute druckt nur die Box selbst. Ein
  Druckknopf am Foto in der Galerie bräuchte eine Freigabe (sonst leert der
  erste Spaßvogel die Farbbandkassette) und eine sichtbare Warteschlange.
- **Download des eigenen Fotos in Originalgröße** — die Galerie liefert heute
  `/img`, `/thumb`, `/preview`; ob ein Handy im Hotspot daraus einen sauberen
  Download macht, ist ungeprüft.
- **Bewegtbild (GIF / Boomerang)** — reizvoll, aber gphoto2 liefert Einzelbilder;
  die Serienaufnahme müsste über die Capture-Card laufen, deren Bild deutlich
  schlechter ist als das der Kamera. Vermutlich mehr Aufwand als Ertrag.

- **Gäste laden ihre eigenen Handyfotos in die Galerie**
  *Heute:* In den Event-Ordner schreibt ausschließlich die Box. Für den Gast
  ist die Galerie lesend; das Einzige, was er verändern darf, ist Löschen —
  und auch das nur mit Admin- oder Host-PIN
  (`gallery_server.py:1020-1043`). Einen Upload gibt es nur im Adminbereich
  für das Logo (`/api/admin/logo`, `gallery_server.py:1507`).
  *Warum reizvoll:* Die besten Bilder des Abends liegen am Ende auf fremden
  Handys — Tanzfläche, Rede, Tortenanschnitt. Alle Gäste sind ohnehin schon im
  Hotspot und kennen die Adresse; der Upload wäre der kürzeste denkbare Weg,
  den Abend an einer Stelle zu sammeln.
  *Was der Code fast fertig hat:* Der Prüfweg für hochgeladene Bilder
  existiert — `/api/admin/logo` nimmt eine Datei entgegen und lässt sie durch
  `PIL.Image.verify()` laufen. Und die Galerie unterscheidet Bildarten bereits
  am Dateinamen (`collage.classify`, `collage.py:40`); Gästebilder bräuchten
  ein eigenes Präfix, damit sie nicht als Box-Einzelfoto durchgehen und in der
  Polaroid-Wand landen.
  *Offen bleibt — und das ist deutlich mehr als der Upload selbst:*
  (1) **Moderation.** Ein offener Upload im Gäste-WLAN heißt: irgendwann liegt
  irgendetwas in der Galerie. Entweder alles in einen Warteraum, den der
  Gastgeber freigibt, oder man akzeptiert es und gibt ihm einen schnellen
  Löschweg — den gibt es mit dem Host-PIN schon.
  (2) **Speicher.** `max_photos` steht auf 500, `disk_monitor` räumt ab
  `photo_max_age_days` auf (`config.py:82,165`), und ab `disk_block_mb`
  blockiert der Auslöser (`main.py:388-391`). Zwanzig Gäste mit vollen
  Kamerarollen sprengen das — Uploads brauchen ein eigenes Kontingent, sonst
  wirft die Automatik Box-Fotos weg, um Handybilder zu behalten. **Der
  Auslöser der Box darf nie wegen fremder Uploads blockieren.**
  (3) **Gehören sie in dieselbe Galerie?** Ein eigener Reiter „Von Gästen"
  wäre ehrlicher als eine Mischung und hielte den Filter „Collagen /
  Einzelbilder" sauber.
  (4) **Nicht druckbar.** Handybilder am Drucker freizugeben leert die
  Farbbandkassette vor Mitternacht — hängt am Nachdruck-Punkt darüber.

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

- **Druck-Warteschlange sichtbar machen**
  *Heute:* `printing.refresh_status` fragt `lpstat -p`, `-e` und `-d` ab
  (`printing.py:67,98,131`) — also *welche* Drucker es gibt und ob der
  gewünschte bereit ist. **Die Jobliste (`lpstat -o`) fragt niemand ab.** Der
  Gast sieht 0,8 s „Wird gedruckt…" und 2,5 s „Foto wird gedruckt"
  (`main.py:132-137`), danach ist er wieder auf dem Homescreen und weiß nichts
  mehr.
  *Was daraus am Eventabend wird:* Der Selphy zieht das Blatt für die
  Farbdurchgänge mehrfach durch und braucht spürbar länger als diese drei
  Sekunden — wie viel genau, ist nicht gemessen; die Generalprobe („20 Drucke
  am Stück") liefert die Zahl. Wer nichts herauskommen sieht, drückt noch
  einmal. Am Ende liegen vier gleiche Bilder in der Kassette, und der nächste
  Gast steht vor einer Schlange, die er nicht sieht.
  *Was fehlt:* Eine Zeile auf dem Result-Screen und im Admin-Panel — „3
  Aufträge vor dir" — plus die Entscheidung, ob der Druck-Knopf ab einer
  gewissen Länge zumacht.
  *Wo das hingehört:* `printing.py` hat den passenden Mechanismus schon, samt
  Begründung: Der Zustand wird gecacht, weil die Renderschleife sonst ~30
  `lpstat`-Forks pro Sekunde auslöst (`printing.py:30-32`, `_STATUS_TTL_S`).
  Eine Queue-Abfrage muss in denselben Cache — nicht als zweiter, ungebremster
  Aufruf daneben.
  *Offen bleibt:*
  (1) **Was „fertig" heißt.** `print_photo` meldet nur, dass CUPS den Auftrag
  angenommen hat (`printing.py:308-313`) — dieselbe Einschränkung wie beim
  Papierzähler darüber. Eine Restzeit aus der Jobzahl ist geschätzt, nicht
  gemessen, und darf nicht als Minutenangabe auftreten, die dann nicht stimmt.
  (2) **Sperren oder nur zeigen?** Gleiche Frage wie beim Kontingent, und
  vermutlich dieselbe Antwort: erst zeigen.
  (3) **Papierstau.** Ein hängender Job blockiert die Schlange dauerhaft.
  Dann braucht es „Warteschlange leeren" im Panel — sonst hilft nur SSH, und
  damit hängt der Punkt am Fernwartungs-Eintrag weiter unten.

- **Der Gastgeber bekommt am Ende alles — ohne dass jemand daran denkt**
  *Heute:* Es gibt zwei Wege aus der Box heraus, und beide braucht jemanden,
  der sie aktiv geht: der USB-Stick (`scripts/usb_export.py`, per udev beim
  Einstecken) und der ZIP-Download in der Galerie (`/api/download-zip`,
  `gallery_server.py:921`, bewusst nur eventweise). Nach einer Feier um drei
  Uhr nachts ist „jemand denkt daran" eine optimistische Annahme — und das
  Panel bietet im selben Atemzug „Alle Fotos löschen" an
  (`AdminMaintenance.tsx`).
  *Denkbar:* Die Box schiebt die Bilder nach dem Event selbst irgendwohin —
  Nextcloud, WebDAV, ein Ordner beim Gastgeber, notfalls eine Mail mit Link.
  Angestoßen aus „Box vorbereiten", das ohnehin der Moment ist, in dem gelöscht
  wird: **löschen darf erst, wer vorher übertragen hat.**
  *Hängt an derselben Frage wie die Fernwartung darunter:* Im Betrieb hat die
  Box kein Internet, sie *ist* der Access-Point. Entweder ein zweiter Uplink —
  oder, viel einfacher, ein Job, der beim nächsten Start im Heim-WLAN
  nachholt, was liegen geblieben ist. Dann braucht es am Eventabend gar nichts.
  *Abgrenzung:* Das automatische Backup (rsync/NAS) in der Roadmap (P3) ist
  etwas anderes — Sicherung gegen Datenverlust, nicht Übergabe an den Kunden.
  Derselbe Transportweg, aber andere Antworten auf „wohin" und „wann darf
  gelöscht werden".
  *Offen bleibt:*
  (1) **Wohin genau?** Eigener Server heißt Pflegeaufwand, Fremddienst heißt
  Abhängigkeit, Mail-Link heißt Speicher trotzdem irgendwo.
  (2) **Datenschutz.** Damit verlassen Gästefotos das Gerät. Bei Vermietung
  gehört das in die Absprache, nicht in ein stilles Häkchen im Panel.
  (3) **Wann darf die Box löschen?** Erst nach bestätigtem, vollständigem
  Transfer — sonst ersetzt ein halb hochgeladener Ordner den vollständigen auf
  der SD-Karte, und das fällt erst auf, wenn niemand mehr etwas retten kann.

- **Bilder direkt in die Cloud sichern, statt erst am Ende**
  *Heute:* Jedes Bild existiert genau einmal — auf der SD-Karte des Pi.
  `camera.capture` (`camera.py:200`) schreibt `foto_<ms>.jpg` in den
  Event-Ordner, `make_collage` legt die fertige Collage daneben, und das war
  es. Geht die Karte kaputt, wird die Box gestohlen oder rutscht sie vom
  Tisch, ist der Abend weg. Gleichzeitig räumt `disk_monitor` selbsttätig
  auf: nach `photo_max_age_days` (7) und ab `max_photos` (500) löscht die
  Box vor jeder Aufnahme ältere Bilder (`main.py:385-397`) — die einzige
  Kopie also, ohne dass jemand zustimmt.
  *Die Idee:* Sobald ein Bild fertig ist, schiebt die Box es hoch — Nextcloud,
  WebDAV, S3, Google Drive, was auch immer. Nicht als Aktion am Ende des
  Abends, sondern als Nebenläufigkeit während des Betriebs.
  *Warum das mehr ist als Backup:* Liegen die Bilder schon oben, während die
  Feier läuft, kann der Gastgeber sie am nächsten Morgen abrufen, ohne dass
  jemand einen USB-Stick eingesteckt hat — und die Frage „darf die Box
  löschen?" beantwortet sich von selbst, weil eine zweite Kopie existiert.
  Aus dem Aufräumen von `disk_monitor` wird damit vom Datenverlust ein
  reines Platzschaffen.
  *Der Haken, der alles bestimmt — es gibt kein Internet:* Die Box *ist* der
  Access-Point (`hotspot_enabled: True`, `config.py:93`), `hotspot.py` legt
  `wlan0` als AP an und trennt in `_free_interface` (`hotspot.py:102`) sogar
  bestehende Client-Verbindungen auf demselben Interface. „Direkt in die
  Cloud" heißt also zuerst: **Uplink besorgen** — zweites WLAN-Interface,
  LTE-Stick, Tethering oder Ethernet. Das ist exakt dieselbe Vorbedingung wie
  bei der Fernwartung darunter; wer den einen Punkt baut, hat den anderen zur
  Hälfte mit.
  *Der ehrliche Ausweg, falls kein Uplink kommt:* Ein Ausgangskorb, der beim
  nächsten Start im Heim-WLAN abgearbeitet wird. Dann ist es kein „direkt"
  mehr, aber der Gastgeber und die Box müssen am Eventabend nichts tun und
  niemand denkt um drei Uhr nachts an einen Stick. Für den Datenverlust
  während der Feier hilft das allerdings nicht — genau dafür ist der Upload
  gedacht.
  *Wo das im Code hängt:* Auf keinen Fall in `_capture_sequence`
  (`main.py:91`) oder `_do_countdown` — dort wartet der Gast bereits auf
  gphoto2, und ein Upload im selben Pfad legt die 30-fps-Renderschleife
  (`main.py:465`) für die Dauer der Netzverbindung still. Der Upload gehört
  in einen eigenen Thread mit Warteschlange, so wie `camera.py` den Watchdog
  nebenher laufen lässt. **Ein Netzfehler darf den Auslöser nie erreichen.**
  *Abgrenzung:* Nicht dasselbe wie „Der Gastgeber bekommt am Ende alles"
  darüber (Übergabe an den Kunden, einmalig, mit Löschsperre) und nicht
  dasselbe wie das automatische Backup (rsync/NAS) in der Roadmap (P3,
  Sicherung im Heimnetz). Der Unterschied ist der Zeitpunkt: hier fällt die
  Kopie während des Events an, nicht danach. Wahrscheinlich sind alle drei am
  Ende **ein** Transportmechanismus mit drei Zielen — und genau so sollte man
  es bauen, statt drei Uploader nebeneinander zu pflegen.
  *Offen bleibt:*
  (1) **Wessen Cloud?** Ein eigener Server heißt Pflegeaufwand, ein
  Fremddienst heißt Abhängigkeit und Zugangsdaten. Bei Vermietung liegen die
  Bilder sonst im Konto des Box-Besitzers, obwohl es die Gäste des Mieters
  sind — dann eher pro Event ein Ziel, das der Gastgeber selbst hinterlegt.
  (2) **Zugangsdaten auf einer vermieteten Box.** Ein Token in `config.json`
  liegt auf einer SD-Karte, die den ganzen Abend in fremder Hand ist. Nicht
  in `_MIETER_FIELDS` (`config.py:16-26`) aufnehmen, ohne vorher zu klären,
  wer es lesen darf — und in `HANDOVER_FIELDS`, damit „Box vorbereiten" es
  für den nächsten Mieter löscht.
  (3) **Datenschutz.** Gästefotos verlassen das Gerät, und zwar während die
  Leute noch davorstehen. Das gehört in die Absprache mit dem Mieter und
  sichtbar ins Panel, nicht in ein stilles Häkchen.
  (4) **Was gilt als „gesichert"?** Erst nach bestätigtem Upload darf
  `disk_monitor` das lokale Bild wegräumen — sonst löscht die Automatik ein
  Foto, dessen Upload nur halb durchging.
  (5) **Was wird hochgeladen?** Nur die Collage oder auch die vier
  Einzelaufnahmen (`collage_<gid>_n.jpg`)? Alles ist ehrlicher, kostet aber
  das Fünffache an Datenvolumen — auf einem LTE-Tarif ist das der
  Unterschied zwischen läuft und läuft nicht.
  (6) **Sichtbarkeit.** Fällt der Upload den ganzen Abend still aus, darf das
  nicht erst am nächsten Tag auffallen. Eine Zeile im Admin-Panel — „12 von
  87 Bildern warten" — ist der Mindestpreis dafür.

- **Fernwartung: an die vermietete Box kommen, ohne hinzufahren**
  *Der Anlass:* Steht die Box beim Mieter und klemmt etwas, ist die einzige
  Antwort heute Hinfahren. Ein Fernzugang wäre die Abkürzung.
  *Der Haken, der alles bestimmt:* **Die Box hat im Betrieb kein Internet.**
  Sie *ist* der Access-Point (`hotspot_enabled: True`, `config.py:93`);
  `hotspot.py` legt `wlan0` als AP mit `ipv4.method=shared` an und trennt in
  `_free_interface` (`hotspot.py:102`) sogar bestehende Client-Verbindungen auf
  demselben Interface, damit der Hotspot sauber hochkommt. Ohne Uplink kein
  Zugriff von außen — das, nicht der SSH-Daemon, ist die eigentliche Aufgabe.
  *Wege zu einem Uplink:*
  (1) **Zweites WLAN-Interface.** `hotspot_interface` ist konfigurierbar
  (`config.py:95`) — der AP läuft auf einem USB-Stick als `wlan1`, `wlan0`
  hängt sich ins Location-WLAN. Setzt voraus, dass es dort eins gibt und
  jemand das Passwort herausrückt.
  (2) **LTE-Stick oder Handy-Tethering über USB** — unabhängig vom Gastgeber,
  kostet aber Hardware und Datentarif.
  (3) **Ethernet**, wenn zufällig eine Dose in Reichweite liegt. Selten.
  *Wie der Zugang aussähe:* Portfreigabe plus DynDNS scheidet praktisch aus —
  an den Router einer fremden Location kommt man nicht. Realistisch ist nur ein
  **ausgehender** Tunnel, den die Box selbst aufbaut (Tailscale, WireGuard auf
  einen eigenen Server, Cloudflare Tunnel). Dann genügt irgendein Internet,
  egal hinter welchem NAT.
  *Was der Anlass schon halb erledigt hat:* Der häufigste Grund für „ich müsste
  jetzt per SSH ran" war der Absturz ohne Neustart. `fotobox.service:17` steht
  inzwischen auf `Restart=on-failure` mit `RestartSec=5`, gebremst durch
  `StartLimitBurst` — offen ist nur noch die Gegenprüfung am echten Gerät
  (Roadmap P0, Punkt 4). Was danach bleibt, ist der seltenere Rest: Logs lesen,
  `config.json` korrigieren, Dienst gezielt neu starten.
  *Der billigere Zwischenschritt:* **Log-Ansicht und Neustart-Knopf im
  Admin-Panel.** Das erreicht der Gastgeber über den Box-Hotspot ganz ohne
  Internet, und ich lotse ihn am Telefon hin. `/api/admin/status`
  (`gallery_server.py:1223`) ist der Anfang, Logs und Neustart fehlen. Deckt
  vermutlich die Mehrzahl der Fälle ab — ohne Uplink, ohne Tunnel, ohne
  Fremddienst im Netz. Ein echter SSH-Zugang wäre dann nur noch für das
  gedacht, was auch das Panel nicht mehr rettet.
  *Offen bleibt:*
  (1) **Vertrauen.** Fernzugriff auf die Box heißt Zugriff auf die Gästefotos
  des laufenden Abends. Key-Auth statt Passwort ist Pflicht, und ehrlich wäre,
  dem Mieter zu sagen, dass es den Zugang überhaupt gibt.
  (2) **Wer schaltet ihn scharf?** Dauerhaft an ist bequem und riskant; nur auf
  Zuruf an ist sauber, braucht aber jemanden vor Ort, der genau diesen Knopf
  drückt — also wieder das Admin-Panel, und damit hängt Punkt 2 an dem
  Zwischenschritt darüber.
  (3) **Fremdabhängigkeit.** Tailscale & Co. sind Dienste Dritter. Wenn der im
  entscheidenden Moment eine Neuanmeldung verlangt, ist nichts gewonnen.

- **Abendbilanz** — Fotos gesamt, Drucke, Spitzenzeit, längste Pause. Die Daten
  liegen ohnehin im Event-Ordner und in den Logs; nützlich für die Frage, wie
  viel Papier beim nächsten Mal mitmuss.
