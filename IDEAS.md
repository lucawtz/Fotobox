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
Umgesetzte genauso wenig: sie bekommen **✅ gebaut TT.MM.JJJJ** in die
Titelzeile, behalten die getroffene Entscheidung und verweisen auf Code und
README. Ein Eintrag, der „denkbar wäre…" schreibt, obwohl es das längst gibt,
schickt den Nächsten auf eine Runde, die schon gedreht wurde.

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

- **Standbild-Dauer im Admin-Panel einstellbar** — *notiert 24.08.2026*
  *Heute:* Sobald gphoto2 für die Aufnahme das USB-Gerät übernimmt, endet der
  Live-View, und die Kamera legt ihr eigenes Aufnahmemenü auf HDMI. Die Box
  zeigt deshalb währenddessen das letzte echte Live-Bild weiter — aber
  höchstens `UI._LIVE_HOLD_S = 8.0` (`ui.py:907`), danach kommt wieder
  „Bitte Display an der Kamera einschalten". Die Zahl steht fest im Code.
  *Warum verstellbar:* Acht Sekunden sind gegen die heutige Aufnahmedauer
  gerechnet (gut zwei Sekunden) plus Reserve für den halbstündlichen Wechsel
  der Halte-Sitzung. Beides verschiebt sich mit anderer Kamera, anderem Kabel
  oder anderer Collage-Länge, und dann ist die richtige Zahl eine andere —
  heute hieße das eine Code-Änderung und ein Deploy.
  *Wo das landet:* ein Feld in `config._DEFAULTS` (`config.py`) neben den
  anderen Kamera-Werten, durchgereicht wie `camera_hold_session_s`.
  Bedienelement im Admin-Panel unter `frontend/src/pages/admin/`, und `UI`
  liest den Wert aus der Config statt aus der Klassenkonstante.
  *Offen bleibt:*
  (1) **Wem der Wert gehört.** `countdown_duration` steht in `_MIETER_FIELDS`
  (`config.py:16`), weil der Gastgeber ihn sinnvoll wählen kann. Die
  Standbild-Dauer ist dagegen eine Eigenschaft der Hardware, nicht des Abends:
  sie hängt daran, wie lange *diese* Kamera für eine Aufnahme braucht. Dann
  gehört sie zu den box-spezifischen Einstellungen und in den Wartungs-Teil
  des Panels — nicht neben Eventname und Countdown.
  (2) **Eine Zahl oder mehrere.** In derselben Ecke stehen zwei weitere feste
  Werte: `_LAECHELN_MAX_MS` (`ui.py:1500`, wie lange „Lächeln!" auf ein
  ausbleibendes Auslöse-Signal wartet) und `capture_lead_s` (`config.py`,
  schon konfigurierbar, aber nirgends im Panel). Drei einzelne Regler für
  Dinge, die alle an derselben Kameraverzögerung hängen, wären drei
  Gelegenheiten, sie widersprüchlich einzustellen. Vielleicht ist der
  ehrlichere Schnitt ein einziger Wert — „wie träge ist diese Kamera" — aus
  dem die Box den Rest ableitet.
  (3) **Obergrenze.** Ein eingefrorenes Bild sieht aus wie ein lebendes. Wer
  60 Sekunden einstellt, baut sich eine Box, die bei toter Kamera minutenlang
  behauptet, alles sei in Ordnung. Das Feld braucht eine Grenze, und die
  Begründung dafür gehört an das Bedienelement.

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

- **Diashow des laufenden Events im Vollbild, wenn die Box ruht** — *notiert 25.08.2026*
  *Heute: das gibt es schon — nur abgeschaltet.* Bleibt der Homescreen
  `idle_timeout` Sekunden ohne Knopfdruck, lädt `main.py:393-396` die Fotos des
  laufenden Events (`events.current_event_dir`) und schaltet in den Zustand
  `SLIDESHOW`. `UI.render_slideshow` (`ui.py:2046`) legt sie über die vollen
  1920×1080, blendet 800 ms lang über (`_SLIDE_FADE_MS`, `ui.py:580`), setzt den
  Galerie-QR unten rechts und lässt „Drück einen Knopf" pulsieren; jeder Taster
  bricht ab (`main.py:519-523`). Der Default ist aber `idle_timeout: 0` — aus
  (`config.py:87`).
  *Was wirklich fehlt, ist also nicht die Diashow, sondern der Weg, sie
  einzuschalten.* `idle_timeout` und `slide_duration_ms` stehen in `_DEFAULTS`
  und **nicht** in `config._MIETER_FIELDS` (`config.py:17-27`). Das Admin-Panel
  kommt nicht an sie heran, und `save_config` würde beide aus einer lokalen
  `config.json` beim ersten Speichern kommentarlos verwerfen. Einschalten heißt
  heute: Code ändern, deployen. Damit liegt ein fertiges Feature brach — das
  README verspricht sogar Default `60` (`README.md:99`), was schlicht nicht
  stimmt (Roadmap-Punkt 19).
  *Kleinster sinnvoller Schnitt:* nur `idle_timeout` ins Admin-Panel, als
  Auswahl „aus · 1 min · 3 min · 5 min", `slide_duration_ms` fest lassen. Eine
  Zahl, die der Gastgeber versteht, statt zweier, die er gegeneinander abwägen
  muss.
  *Offen bleibt:*
  (1) **Wem der Wert gehört.** Ob die Box in der Pause Bilder zeigt, ist eine
  Eigenschaft des Abends — dann `_MIETER_FIELDS` **und** `HANDOVER_FIELDS`
  (`config.py:75`), damit „Box vorbereiten" sie für den nächsten Gastgeber
  zurücksetzt. Gegenargument, das mitgeschrieben gehört: Eine Diashow zeigt die
  Fotos der letzten Gäste großflächig und ungefragt. Auf der Firmenfeier ist
  das gewollt, auf anderen Feiern genau nicht — der sichere Default bleibt
  „aus", eingeschaltet wird bewusst.
  (2) **Was gezeigt wird, stimmt noch nicht.** `refresh_slideshow`
  (`ui.py:2031`) nimmt jede `.jpg/.jpeg/.png` aus dem Eventordner. Dort liegen
  neben jeder fertigen Collage aber auch ihre vier Quellaufnahmen
  (`collage_<gid>_1..4.jpg`, `collage.py:6-8`) — dasselbe Gesicht viermal
  hintereinander und danach nochmal als Collage. Das Werkzeug dagegen existiert
  schon: `collage.classify` (`collage.py:40`) trennt `KIND_MEMBER` von
  `KIND_SINGLE`/`KIND_COLLAGE`, die Galerie filtert damit bereits.
  (3) **Die Reihenfolge ist keine.** `sorted()` über die Dateinamen ist
  alphabetisch, und die Namen sind `collage_<ms>.jpg` bzw. `foto_<ms>.jpg`
  (`collage.py:115`, `camera.py:512`) — es laufen also erst *alle* Collagen des
  Abends, dann *alle* Einzelfotos. Chronologisch wäre nach dem Zeitstempel im
  Namen zu sortieren; „neueste zuerst" ist vermutlich noch besser, weil der
  Gast das Bild sucht, das er gerade gemacht hat.
  (4) **Seitenverhältnis.** `smoothscale(img, (W, H))` (`ui.py:2061`) zieht
  jedes Bild auf 16:9, die Kamera liefert 3:2 — Gesichter werden breit gezogen.
  Für die Polaroids macht `UI._scale_to_fill` es richtig; die Diashow müsste
  denselben Weg gehen (beschneiden statt verzerren) oder mit Balken leben.
  (5) **Was die Kamera derweil tut** — ungeprüft. Der Live-View läuft während
  der Diashow weiter, obwohl ihn niemand sieht: über eine lange Pause hinweg
  Akku und eine gehaltene USB-Sitzung für nichts. Die Diashow wäre der
  natürliche Moment, die Kamera schlafen zu legen — aber nur, wenn sie beim
  ersten Knopfdruck schnell genug zurückkommt. Sonst tauscht man unsichtbaren
  Verbrauch gegen sichtbare Wartezeit, und das ist ein schlechter Tausch.
  *Nicht kaputtmachen:* Hat an diesem Abend noch niemand fotografiert, fällt
  `render_slideshow` auf den Homescreen zurück (`ui.py:2048-2050`) — eine leere
  Box startet keine leere Diashow.

- **Pausemodus — „gleich wieder da"** — *notiert 09.09.2026, Ausgestaltung offen*
  *Heute:* Die Box kennt genau einen Zustand: läuft. Der Halte-Prozess hält die
  PTP-Sitzung und damit den Live-View dauerhaft offen (`camera.py`), und
  `idle_timeout` steht per Default auf `0`, also aus (`config.py`). Beim Essen
  und während der Reden steht sie deshalb eine Stunde mit laufendem Live-Bild,
  offener USB-Sitzung und leerlaufendem Kamera-Akku da — für niemanden.
  *Denkbar:* Ein Knopf im Admin-Panel schaltet auf Pause. Der Boxschirm zeigt
  einen Hinweis statt des Live-Bildes, die Taster lösen nicht aus, die Kamera
  darf schlafen. Zurück per Panel oder per Tastendruck an der Box.
  *Der Haken, der die Idee zuschneidet:* Ob der Live-View wirklich fallen darf,
  ist die eigentliche Frage. Ihn zurückzuholen dauert (`HARDWARE.md`,
  „Live-Bild nach dem Stromzyklus"), und der erste Gast nach der Pause steht
  dann vor einem schwarzen Schirm. Eine Pause, die den Live-View *hält* und nur
  die Oberfläche umschaltet, ist die sichere Variante — spart dafür weder Akku
  noch USB-Sitzung, also genau das, wofür sie gedacht war.
  *Verhältnis zur Diashow darüber:* Beide beantworten dieselbe Stunde
  verschieden — die Diashow füllt sie, die Pause räumt sie weg. Sie schließen
  sich nicht aus (Pause könnte die Diashow zeigen), sollten aber zusammen
  entschieden werden, sonst baut man zwei Ruhezustände nebeneinander.
  *Offen:* Wer schaltet zurück? Was steht auf dem Schirm — ein Text des
  Gastgebers oder eine feste Zeile? Soll die Pause von selbst enden?

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
- **Web-Größe für Gäste statt Originalgröße** — *durchgerechnet 25.08.2026*
  *Heute:* Die Galerie liefert `/thumb` (400 px, ~30 KB), `/preview` (1280 px,
  ~300 KB) und `/img` bzw. `/download` — letztere das unveränderte
  Kameraoriginal, bei der 700D **4–5 MB**. Der Einzeldownload ist bewusst der
  einzige Weg, den ein Gast hat: das Gesamt-ZIP ist seit 25.08.2026 dem
  Gastgeber und dem Besitzer vorbehalten (`gallery_server.py:1170`).
  *Das Problem:* Der Hotspot schafft real rund 3 MB/s für **alle zusammen**
  (2,4 GHz, `band=bg`/Kanal 6 fest verdrahtet, `hotspot.py:244`). Speichern
  30 Gäste je fünf Bilder, sind das 675 MB — gut vier Minuten, in denen sonst
  nichts mehr durchkommt. Nicht mehr fatal wie das ZIP, aber auch nicht nichts.
  *Die Idee:* Gästen eine dritte Größe anbieten — 2048 px, Quality 85, ~600 KB.
  Auf jedem Handydisplay und für Instagram vom Original nicht zu unterscheiden,
  aber **Faktor 7 weniger Last**. Das echte Original bleibt dem Gastgeber und
  dem USB-Weg vorbehalten. Technisch billig: `_render_cached`
  (`gallery_server.py:107`) kann das schon, es braucht nur eine weitere Route
  neben `/preview` und die Entscheidung, welche Rolle welche Größe bekommt.
  *Offen bleibt:*
  (1) **Sagt man es dem Gast?** Ein stilles Herunterrechnen ist bequem, aber
  unehrlich gegenüber jemandem, der „Original" liest. Entweder ehrlich
  beschriften oder die Wahl lassen.
  (2) **Was ist mit Drucken?** Wer das Bild später selbst ausbelichten lässt,
  will die 5 MB. Das ist genau der Fall, für den der Gastgeber das ZIP hat —
  aber ein Gast, der es direkt will, steht dann ohne da.
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

- **Papierkorb statt Sofortlöschen** — *notiert 09.09.2026, bewusst klein gehalten*
  *Heute — und das korrigiert die Annahme, aus der die Idee entstand:* Gäste
  können **gar nichts löschen**. `api_delete` verlangt eine offene Session oder
  Admin-/Host-PIN im Formular (`gallery_server.py:1367-1390`); ohne PIN kommt
  403. Der Löschknopf ist zwar für jeden sichtbar, der Dialog fragt dann aber
  nach der PIN (`DeleteDialog.tsx`). Die Idee war ursprünglich mit „ein Gast
  vertippt sich" begründet — das kann nicht passieren.
  *Was bleibt:* Der Fehlgriff des Gastgebers. Spätabends auf dem Handy, beim
  Aufräumen, das falsche Bild erwischt. `os.remove` ist endgültig
  (`gallery_server.py:1401`), Thumbnail und Preview gehen im selben Zug mit.
  *Denkbar:* Ein `.trash`-Unterordner im Event-Verzeichnis statt `os.remove`,
  sichtbar nur für den Admin, geleert bei der Übergabe
  (`api_admin_handover`) und vom Alters-Cleanup miterfasst
  (`disk_monitor.enforce_photo_max_age`) — sonst wächst ein Ordner, den
  niemand ansieht.
  *Warum das klein bleiben soll:* Der Fall ist selten und trifft genau die
  Person, die weiß, was sie getan hat. Ein sichtbarer Papierkorb in der Galerie
  wäre die falsche Antwort — er zeigt gelöschte Bilder wieder her, und
  „gelöscht" soll für Gäste gelöscht heißen. Niedrige Priorität, nach Oktober.

## Betrieb

- **Papierzähler und Druckkontingent** — ✅ **gebaut 09.09.2026** (Zähler;
  Kontingent bewusst nicht)
  *Was daraus wurde:* `paper.py` zählt jeden Auftrag mit, den CUPS annimmt,
  angestoßen aus `printing.print_photo`. Stand in `.paper_state.json` neben der
  `config.json`, Anzeige im Admin-Panel (Drucken → Papiervorrat) und in der
  Statusleiste der Box, Warnschwelle `paper_warn_at`. Beschrieben im README
  unter „Papiervorrat".
  *Die Haken von damals sind so eingebaut, wie sie hier standen:* Der Zähler
  addiert die **Kopienzahl**, nicht eins (`printing._copies` liefert dieselbe
  Zahl an lp und an den Zähler). Er ist als **Schätzung** ausgewiesen — überall
  steht „ca." — und im Panel von Hand korrigierbar („Nachgezählt"), weil
  Papierstau und abgebrochene Aufträge ihn driften lassen.
  *Die offene Frage ist entschieden: nur warnen, nicht sperren.* Ob wirklich
  Papier da ist, weiß allein der Drucker (`media-empty`); ein Zähler, der auf 0
  steht, während die Kassette voll ist, darf den Drucken-Knopf nicht wegnehmen.
  *Was offen blieb:* (1) Das **Kontingent** selbst — eine Obergrenze pro Abend
  oder pro Gast gibt es nicht, und damit auch die Sperrfrage nicht. (2) Ob der
  Drucker doch einen echten Füllstand liefert (`marker-levels`), ist ungeprüft;
  die Prüfbefehle stehen in `HARDWARE.md` im Abschnitt Drucker. (3) Die Anzeige
  auf dem Boxmonitor blendet mit der Statusleiste nach 30 s aus — dauerhaft
  sichtbar ist sie nicht.

- **Zweitkopie auf die Speicherkarte der Kamera** — *Wunsch 09.09.2026 (Luca):
  vorhandene 16-GB-Karte als Backup, Bilder dort nach einem Monat automatisch
  weg*
  *Heute:* `capturetarget` steht auf **Internal RAM** (`HARDWARE.md`, Abschnitt
  Kamera) — die Karte wird nicht beschrieben, `--capture-image-and-download`
  holt das Bild aus dem internen Speicher (`camera.py:568`). Das einzige Backup
  ist der manuelle USB-Export (`scripts/usb_export.py`); die Roadmap führt
  „Automatisches Backup (rsync/NAS)" als offenen P3-Punkt.
  *Was es brächte:* Eine Kopie, die weder Pi noch Netz noch diese Software
  braucht. 16 GB fassen bei Large Fine JPEG der 700D grob 2000 Bilder, also
  mehrere Events — Platz ist nicht das Thema. Der Wert ist die Unabhängigkeit:
  stirbt die SD-Karte des Pi zwischen Feier und Übergabe, ist der Abend
  trotzdem da.
  *Der Haken, direkt aus dem Code:* `camera.py:705-717` nennt „capturetarget
  zeigt auf die Speicherkarte statt auf den internen Speicher" ausdrücklich als
  eine der zwei bekannten Ursachen für *„Kamera hat kein Bild geliefert"* —
  früher lief die Box damit in einen schwarzen Result-Screen ohne Erklärung.
  Die Umstellung fasst also genau die Stelle an, an der die Aufnahme schon
  einmal still gescheitert ist. **Vor der Generalprobe testen, nicht danach**,
  und der Auslöser ist der eine Pfad, der niemals wackeln darf.
  *Ungeprüft, gehört gemessen:* (a) ob `--capture-image-and-download` mit
  Kartenziel die Datei auf der Karte liegen lässt oder sie nach dem Download
  entfernt (gphoto2 kennt dafür `--keep`); (b) ob die Auslöseverzögerung steigt
  — sie ist gemessen und `capture_lead_s` hängt daran.
  *Löschen nach einem Monat — der schwierige Teil:* Die Karte ist nur über
  dieselbe PTP-Sitzung erreichbar, die der Halte-Prozess offen hält. Ein
  paralleler `gphoto2`-Aufruf kollidiert (`HARDWARE.md`: „Dienst vorher
  stoppen, sonst hält der Halte-Prozess das Gerät"). Das Aufräumen muss also in
  das Fenster, in dem der Halter ohnehin neu startet — nicht als eigener Job
  daneben. Werkzeug wäre `--list-files` / `--delete-file` je Kameraordner.
  Fällt das Aufräumen aus, ist das kein Drama: die Karte läuft erst nach
  Tausenden Bildern voll. Es darf nur nie die Aufnahme aufhalten.
  *Bewusst hinzunehmen — die Asymmetrie:* Der Pi löscht nach
  `photo_max_age_days` (7 Tage), die Karte soll vier Wochen halten. Das ist der
  Sinn eines Backups, heißt aber auch: die Fotos einer fremden Feier liegen
  drei Wochen länger in der Kameratasche als auf der Box, die sie aufgenommen
  hat. Wer die Box vermietet, sollte das wissen.
  *Offene Frage:* Bei der Übergabe an den nächsten Gastgeber die Karte
  mitleeren (`api_admin_handover` hakt heute Fotos, Branding und Logo ab)? Das
  wäre konsequent, verkürzt aber genau die Frist, für die das Backup da ist.
  *Nebenfund:* Die Kamerauhr geht 3602 s nach (`HARDWARE.md`, Abschnitt Uhr).
  Für eine Monatsgrenze egal, für die Sortierung der Kartendateien nicht.

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

- **Welcher Verteilweg für wen — die Entscheidung über den drei Einträgen unten**
  *Warum das hier oben steht:* Die drei Punkte darunter (Übergabe an den
  Gastgeber, Cloud-Upload, Fernwartung) beantworten alle dieselbe Frage
  verschieden, ohne dass irgendwo steht, **wer eigentlich welchen Weg
  bekommt**. Ohne diese Entscheidung baut man am Ende drei Uploader für drei
  Zielgruppen. Aufgeschrieben nach dem Durchrechnen der Galerie-Last am
  25.08.2026.
  *Die vier Kandidaten sortiert:* **USB-Stick** und **Datenvolumen** sind gar
  keine Gast-Auslieferungswege. USB (`scripts/usb_export.py`, per udev) ist der
  Weg für *dich und den Gastgeber* — 2,25 GB Originale in einer Minute, kein
  Netz beteiligt, nichts kann überlasten. Ein LTE-Stick ist kein Verteilweg,
  sondern nur ein Uplink für die Cloud-Variante; Gäste dahinter zu routen wäre
  ein zweiter Flaschenhals hinter dem ersten, und zwar einer, der pro GB kostet.
  Bleibt die echte Wahl: **lokaler Hotspot** oder **Cloud/eigene Webseite**.
  *Der Punkt, der alles entscheidet — der Zeitpunkt des Uploads:* Cloud klingt
  nach der stabilsten Lösung und ist am Eventabend die **fragilste**. 500
  Originale sind 2,25 GB; bei optimistischen 5 Mbit/s LTE-Upload sind das gut
  **60 Minuten** über eine Leitung, die in einer Scheune jederzeit abreißt.
  Lädt man dagegen am **nächsten Tag von zuhause** hoch, ist die Netzqualität
  der Location schlagartig irrelevant — dieselbe Technik wird von der
  unzuverlässigsten zur zuverlässigsten Variante, allein durch Verschieben des
  Zeitpunkts. Das ist genau der „Ausgangskorb, der beim nächsten Start im
  Heim-WLAN abgearbeitet wird" aus dem Cloud-Eintrag unten — dort noch als
  *Notlösung, falls kein Uplink kommt* beschrieben. Für die **Gästeverteilung**
  ist er nicht die Notlösung, sondern die bessere Antwort. (Für den Schutz
  gegen Datenverlust *während* der Feier bleibt er wertlos — das ist der Teil,
  für den der Uplink wirklich gebraucht wird.)
  *Was der lokale Hotspot kann, was keine Cloud kann:* Er funktioniert im
  Gewölbekeller, in der Scheune und im Festzelt — also genau dort, wo
  Hochzeiten stattfinden und wo kein Netz ist. Nach dem Galerie-Umbau vom
  25.08.2026 trägt er die Last auch: Previews à ~300 KB, 30 stöbernde Gäste
  erzeugen grob 1 MB/s auf einem Hotspot, der rund 3 schafft. Lokal ist für den
  Moment der Feier **kein Kompromiss, sondern die zuverlässigste Variante, die
  es gibt.**
  *Die Aufteilung, die sich daraus ergibt:*
  (a) **Während der Feier → lokal.** Kein Internet, keine Abhängigkeit, keine
  laufenden Kosten, kein Datenschutzthema.
  (b) **Bei der Übergabe → USB.** Originale an den Gastgeber. Gibt es schon.
  (c) **Danach → Event-Seite mit eigenem Link,** hochgeladen von zuhause. Löst
  „Gast war da, hat vergessen zu speichern, fragt drei Tage später" und ist
  gleichzeitig ein sauberes Upsell.
  *Falls (c) doch am Eventabend laufen soll:* nur die **Previews** hochladen,
  nicht die Originale — 150 statt 2250 MB, also ~4 Minuten statt einer Stunde.
  Das geht auch über eine wacklige Leitung. Originale bleiben lokal und gehen
  per USB raus. Das beantwortet nebenbei Frage (5) im Cloud-Eintrag unten.
  *Offen bleibt:*
  (1) **Ist (c) Produkt oder Gefallen?** Als Upsell braucht es Preis,
  Löschfrist und eine Zusage, wie lange der Link lebt. Als Gefallen wird es
  die Sorte Aufgabe, die man in drei Jahren noch für Kunden von damals macht.
  (2) **Datenschutz spricht klar für lokal.** Solange nichts die Box verlässt,
  existiert das Thema nicht. Sobald Fotos identifizierbarer Personen auf
  fremden Servern liegen, kommt man als Vermieter in Auftragsverarbeitung,
  Löschfristen und Einwilligungen. Machbar, aber es ist Arbeit und Haftung, die
  (a) und (b) komplett sparen. Vor der ersten Hochzeit in der Cloud gehört da
  echter Rat eingeholt, nicht die Einschätzung eines Entwicklerwerkzeugs.
  (3) **Verträgt sich (c) mit `photo_max_age_days: 7`?** Die Box räumt nach
  einer Woche selbst auf (`photo_max_age_days`, `config.py:232`). Wenn der Upload
  von zuhause erst danach passiert, ist nichts mehr da. Entweder die Frist an
  den Upload koppeln oder den Upload an die Übergabe.

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

- **WLAN-Uplink im Panel: die Box ins vorhandene WLAN bringen** — *Hardware geprüft 25.08.2026*
  *Der Anlass:* Zwei Dinge, die heute an einem Kabel hängen. **Setup ohne
  Kabel** — an die Box kommt man aktuell nur per LAN oder über das
  `--no-hotspot`-Gefummel (`main.py:272`), obwohl `git pull` und ein Blick in
  die Logs die häufigste Wartung überhaupt sind. Und **Backup während der
  Feier** — der Uplink ist die unausgesprochene Vorbedingung der beiden
  Einträge darunter (Cloud-Sicherung, Fernwartung); ohne ihn sind beide
  unbaubar.
  *Ausdrücklich NICHT das Ziel:* Gäste bekommen kein Internet, und die Galerie
  wird davon nicht schneller. Beides begründet unter *Warum Gäste außen vor
  bleiben*.
  *Die Hardware ist da und ist vermessen* (`lsusb` / `iw list` am Gerät,
  25.08.2026). Der Stick ist ein **TP-Link TL-WN823N v2/v3 (RTL8192EU)**:

  | | Stick (RTL8192EU) | intern (Broadcom) |
  |---|---|---|
  | Bänder | nur 2,4 GHz | 2,4 **und 5 GHz** (VHT, bis 80 MHz) |
  | Streams | MCS 0-15 → 2 | MCS 0-7 → 1 |
  | AP-Mode | ja | ja |
  | AP+STA zugleich | „interface combinations are not supported" | ja, aber `#channels <= 1` |

  *Was daraus folgt:* AP und Uplink auf **einem** Chip scheiden aus. Der Stick
  kann die Kombination laut Treiber gar nicht; der interne Chip könnte, aber
  nur auf **einem** Kanal — der Hotspot müsste dem Location-WLAN auf dessen
  Kanal folgen, statt auf dem festen Channel 6 (`hotspot.py:230-231`) zu
  bleiben. Das ist kein Betrieb, auf den man eine Hochzeit stellt.
  *Die Aufteilung:* **Uplink auf den Stick** — `managed` reicht, 2,4 GHz reicht,
  und während des Events ist der Traffic ohnehin fast null. Damit ist auch
  egal, dass `rtl8xxxu` im AP-Mode einen zweifelhaften Ruf hat: wir nutzen den
  Mode nicht. **AP bleibt auf dem internen Chip** — bewährter `brcmfmac`-Pfad,
  läuft heute schon, und er teilt sich den USB-Bus nicht mit gphoto2 und der
  Canon. Der Auslöser ist der eine Pfad, der niemals warten darf.
  *Warum Gäste außen vor bleiben — der Punkt, der die Idee zuschneidet:*
  `ipv4.method=shared` würde eine Default-Route durchaus weiterreichen. Aber
  `captive.conf` schreibt `address=/#/<ip>` (`hotspot.py:36`): der dnsmasq am
  Hotspot beantwortet **jeden** Namen mit der Box-IP. Ein Gast kann also nichts
  außer der Fotobox auflösen. Gäste-Internet und Captive-Portal schließen sich
  aus, solange der Hijack pauschal ist — und das Portal ist der Grund, warum
  der Galerie-Link ohne Abtippen aufgeht. Nicht dafür opfern.
  *Der Nebenfund, der schon heute weh tut — die Uhr:* Der Pi hat keine
  batteriegepufferte RTC. Ohne Netz kommt die Zeit aus `fake-hwclock`, also vom
  letzten Herunterfahren. Stand die Box zwei Wochen im Schrank, glaubt sie in
  der Scheune, es sei vor zwei Wochen — und daran hängt der Event-Ordnername
  (`events.py:184`, `%Y-%m-%d_slug`), die 18h-Session-Logik
  (`event_session_hours`) und jeder EXIF-Zeitstempel. Zwei Minuten Uplink beim
  Aufbau heilen das. Kein Zukunftsthema, sondern ein bestehender Fehler.
  *Zwei Stufen, die erste lohnt allein:*
  (1) **Setup-WLAN.** Verbinden, Hotspot pausiert dabei bewusst, Status +
  Trennen. Braucht keinen Stick und keine neue Hardware — nur `nmcli device
  wifi list/connect` und den vorhandenen `_restart_hotspot_async`-Mechanismus
  (`gallery_server.py:1796`) rückwärts. Deckt „Setup ohne Kabel" komplett ab.
  (2) **Parallelbetrieb** mit dem Stick als Uplink. Erst das macht Backup
  während der Feier und Fernwartung überhaupt baubar.
  *Was ins Panel gehört:*
  (a) **Netz-Scan**, hart ans Uplink-Interface gebunden
  (`nmcli -f SSID,SIGNAL,SECURITY device wifi list ifname <uplink> --rescan yes`).
  Ein Rescan auf dem AP-Interface reißt den Hotspot kurz weg.
  (b) **SSID manuell eintragbar** (versteckte Netze) plus Passwort.
  (c) **Ehrlicher Status:** verbunden / Signal / IP / Gateway — und davon
  getrennt ein echter Reachability-Check nach außen. Bei Hotel- und
  Gäste-WLANs mit eigenem Portal heißt „verbunden" gerade *nicht* „Internet".
  (d) **Fehler im Klartext.** nmcli meldet bei falschem Passwort „Secrets were
  required" — das gehört angezeigt, sonst rät man.
  (e) **Gespeicherte Netze** (Heim-WLAN + Location) mit Trennen/Vergessen.
  (f) **Umbenennen.** Zwei Dinge namens „WLAN" auf einer Seite verwirren:
  „Fotobox-WLAN" (was Gäste sehen, heute `AdminWifi.tsx`) vs.
  „Internet-Verbindung" (was die Box nutzt).
  *Fallstricke, alle aus dem bestehenden Code:*
  (1) **Beide Connections per MAC binden** (`802-11-wireless.mac-address`),
  nicht per `ifname`. USB-Interface-Namen sind nicht stabil — heißt der Stick
  nach einem Reboot `wlan0`, landet der AP auf dem Uplink-Adapter. Ein Fehler,
  der genau einmal auftritt, und zwar auf einer Hochzeit.
  (2) **`_free_interface` (`hotspot.py:132`)** trennt heute jede
  Client-Verbindung auf dem AP-Interface. Muss das Uplink-Interface in Ruhe
  lassen — tut es, solange es strikt nach `ifname` filtert.
  (3) **`_purge_self_ssid_clients` (`hotspot.py:178`)** löscht Profile auf der
  eigenen SSID. Darf das Uplink-Profil nicht erwischen; greift nur bei
  identischer SSID, also nur prüfen, nicht umbauen.
  (4) **Subnetz-Kollision.** Liefert das Location-WLAN 192.168.4.x, kollidiert
  es mit `hotspot_ip` (`config.py:94`) und das Routing bricht. Beim Verbinden
  prüfen und warnen statt still scheitern.
  (5) **Fremdes Passwort auf vermieteter Box.** Nicht in `_MIETER_FIELDS` und
  am besten gar nicht in `config.json` — NetworkManager legt es selbst nach
  `/etc/NetworkManager/system-connections` (0600, root). Nur SSID/Profilnamen
  merken, und das Location-Profil bei „Box vorbereiten" (`HANDOVER_FIELDS`,
  `config.py:74`) mit löschen.
  (6) **Exposure.** Der Galerie-Server bindet auf 0.0.0.0 (`main.py:287`). Mit
  Uplink hängt das Admin-Panel auch im fremden Location-Netz, nur durch die PIN
  geschützt. Bewusste Entscheidung, keine Nebenwirkung.
  *Offen bleibt:*
  (1) **Welches Interface ist heute `wlan0`?** Der Kommentar in
  `hotspot.py:184-185` nimmt an, der Stick sei `wlan1` — die phy-Nummerierung
  (`phy0` = RTL8192EU) deutet aufs Gegenteil, dann liefe der AP heute schon auf
  dem Stick. `iw dev` am Gerät klärt das und dreht ggf. die halbe Planung um.
  (2) **Wohin sichert das Backup?** Dieselbe offene Frage wie im Cloud-Eintrag
  darunter — eigener Server vs. Fremddienst, und wessen Konto bei Vermietung.
  Der Uplink ist nur der Transportweg, nicht die Antwort darauf.
  *Abgrenzung:* Dass der interne Chip laut `iw list` auch **5 GHz AP** kann
  (VHT80 statt heute `band=bg`/Channel 6), ist ein Fund aus derselben Messung,
  aber ein anderes Thema — Galerie-Durchsatz. Gehört nicht in diesen Eintrag
  und braucht weder Stick noch Uplink.

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
