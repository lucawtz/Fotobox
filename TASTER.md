# Fotobox — Taster verdrahten

Welche Ader an welchen Pin gehört, und warum es zwei Abende gekostet hat, das
herauszufinden. Gemessen am **05.09.2026** am laufenden Gerät.

Ergänzt [HARDWARE.md](HARDWARE.md), das nur den Ist-Zustand der GPIO-Belegung
festhält. Hier steht der Weg dorthin.

---

## Die Kurzfassung

| Taster | Ader | Kontakt | Pin | GPIO |
|---|---|---|---|---|
| **Blau** — Foto-Auslösen | **schwarz** | `C` | **9** | GND |
| | **blau** | `NO` | **13** | GPIO27 |
| **Grau** — Collage / Drucken | **weiß** | `C` | **14** | GND |
| | **grün** | `NO` | **15** | GPIO22 |

Und die LED-Ringe, als Dauerlicht ohne Code:

| Taster | Ader | | Pin |
|---|---|---|---|
| **Blau** | **grün** | LED **+** | **1** (3,3 V) |
| | gelb | LED − | **6** (GND) |
| **Grau** | **schwarz** | LED **+** | **17** (3,3 V) |
| | rot | LED − | **20** (GND) |

Der `NC`-Kontakt bleibt bei beiden frei — rot am blauen, blau am grauen. Die
Zielbelegung `trigger=27`, `right=22` steht in `config.py` unter `gpio_pins`.

---

## Die beiden Taster sind unterschiedlich belegt

Beide sind beleuchtete Metall-Drucktaster mit **fünf Adern** an einem
Rundstecker: drei Schaltkontakte (`C`, `NO`, `NC`) und zwei für die LED.
Unterschieden werden sie nach der **Steckerfarbe**.

**Die Adernfarben bedeuten bei den beiden nicht dasselbe.** Blau ist einmal
`NO` und einmal `NC`, schwarz einmal `C` und einmal LED. Wer die Belegung des
einen auf den anderen überträgt, verdrahtet zwangsläufig falsch.

### Taster Blau

Adern: gelb, schwarz, rot, blau, grün. Kontaktblock beschriftet `1 NO 2` / `3 NC 4`.

| Ader | Kontakt |
|---|---|
| schwarz | **`C`** |
| blau | **`NO`** |
| rot | `NC` |
| **grün** | LED **+** |
| gelb | LED − |

### Taster Grau

Adern: weiß, schwarz, rot, blau, grün. Beschriftung wirkt spiegelbildlich.

| Ader | Kontakt |
|---|---|
| weiß | **`C`** |
| grün | **`NO`** |
| blau | `NC` |
| **schwarz** | LED **+** |
| rot | LED − |

---

## Was nicht angeschlossen werden darf

**Der `NC`-Kontakt.** Er ist im Ruhezustand *geschlossen*. An einem GPIO mit
Pull-up zieht er den Pin dauerhaft auf `lo`, und `hardware.Buttons` liest das
als festgehaltenen Knopf — die Box hinge in einer Endlos-Auslösung.

**Die LED an einen GPIO.** Sie leuchtet dort prinzipiell nicht: der interne
Pull-up hat rund 50 kΩ, bei ~2 V Flussspannung fließen daraus etwa **26 µA**.
Eine LED braucht 5–20 mA, also einen Faktor von mehreren hundert mehr.

Dazu kommt: **die Software steuert überhaupt keine LED an.** In `hardware.py`
werden ausschließlich `Button`-Objekte angelegt, LED-Code gibt es im Repo
nirgends. Als Dauerlicht gehören die LEDs an die Versorgung, nicht an einen
GPIO — siehe unten.

---

## Verdrahtung am Header

Ein Schaltkontakt hat **keine Polarität** — welche der beiden Adern auf den
GPIO und welche auf GND geht, ist gleichgültig. Was zählt, ist das *Paar*.

```
POWER-IN-Ecke
 |
 v
Spalte    1     2     3     4     5     6     7     8
        ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
innen   │( 1) │( 3) │( 5) │( 7) │( 9) │(11) │(13) │(15) │
        │3,3V │     │     │     │ GND │     │GPIO27│GPIO22│
        ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
außen   │( 2) │( 4) │( 6) │( 8) │(10) │(12) │(14) │(16) │
        │ 5V  │ 5V  │ GND │     │     │     │ GND │     │
        └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
```

Die **innere Reihe** trägt die ungeraden Pins — dort sitzt die `1`. Der Pi
zeichnet den Header selbst, wenn man unsicher ist:

```
venv/bin/pinout
```

Spalte 1 und 2 der äußeren Reihe sind **5 V**. Eine Ader, die dort landet und
über den Taster auf einen GPIO trifft, speist 5 V in einen 3,3-V-Eingang.

---

## LED-Ringe

Am **05.09.2026** angeschlossen und in Betrieb gesehen. **Beide leuchten an
3,3 V**, es sind also Niedervolt-Typen (3–6 V), keine 12- oder 24-V-Ringe.

| Taster | LED **+** | LED − | Pins |
|---|---|---|---|
| **Blau** | **grün** | gelb | 1 / 6 |
| **Grau** | **schwarz** | rot | 17 / 20 |

Pin 1 und 17 sind die einzigen beiden 3,3-V-Pins am Header — jeder Taster
bekommt einen, so muss keine Ader gespleißt werden. **Pin 1 hat 5 V als
direkten Nachbarn** (Pin 2, dieselbe Spalte, äußere Reihe); eine verrutschte
Hülse legt dort 5 V an die LED.

Die LEDs leuchten damit, sobald der Pi Strom hat — auch beim Booten und nach
dem Herunterfahren, solange das Netzteil steckt. Nebeneffekt: ein brauchbarer
Betriebsindikator.

**Ein Vorwiderstand ist eingebaut, extern sitzt keiner.** Der Nachweis ist der
graue Taster: er *glimmt* an 3,3 V. Ohne internen Widerstand wäre eine LED
direkt zwischen 3,3 V und GND nicht schwach, sondern grell — und bei roter
Flussspannung (~2 V) hätte sie den Einschaltmoment kaum überlebt.

**Der blaue leuchtet deutlich kräftiger als der graue.** Es sind zwei
verschiedene Modelle — unterschiedliche Adernfarben, spiegelbildliche
Beschriftung, also auch unterschiedlich ausgelegte Vorwiderstände. Der graue
ist offensichtlich für mehr als 3,3 V gedacht.

Zwei Folgerungen daraus:

- **Grau darf auf 5 V** (Pin 2 oder 4), falls er zu dunkel ist. Reserve ist
  nachgewiesen.
- **Blau nicht.** Dass er an 3,3 V schon kräftig leuchtet, heißt: kleiner
  Vorwiderstand, wenig Reserve. Er tut ohnehin, was er soll.

Beim blauen lohnt eine Kontrolle, weil die Box abends stundenlang läuft und
eine überfahrene LED über Stunden degradiert, nicht in Sekunden: eine
Viertelstunde leuchten lassen, dann die Metallfront anfassen. Kühl oder
handwarm ist in Ordnung. Deutlich warm heißt, es gehören 100–220 Ω in Reihe.

Geschaltet werden könnten die LEDs über GPIO17 (Pin 11) und einen zweiten
freien GPIO — dann aber mit Code in `hardware.py` und `main.py`, und ab etwa
10 mA mit einem Transistor davor, weil der Pi-Pad standardmäßig nur 8 mA
treibt.

---

## Einen unbekannten Taster ausmessen

Nicht paarweise raten. Bei fünf Adern gibt es zehn Paare, und nur eines ist
`C`+`NO` — blind greifen trifft mit 10 %.

Stattdessen **alle fünf Adern gleichzeitig** auf den Header, dann messen. Die
Pegel liest `pinctrl`, ohne die Leitung zu belegen; `fotobox.service` darf
dabei weiterlaufen:

```
pinctrl get 0-27
```

Zwei Messarten werden gebraucht, und die zweite ist die entscheidende:

**Direkt lesen** findet nur Kontakte, bei denen ein Ende auf **GND** liegt.
Alle Pins auf Pull-up, dann fällt der Partner beim Schließen auf `lo`.

**Kreuztest** findet Kontakte zwischen **zwei GPIOs**. Reihum je einen Pin als
Ausgang auf Masse legen (`pinctrl set <pin> op dl`), die übrigen mit Pull-up
mitlesen, danach zurück auf `ip pu`. Ohne diesen Schritt bleibt ein Taster
unsichtbar, dessen beide Adern auf GPIOs stecken — beide sind hochgezogen, und
das Schließen ändert nichts.

Auswertung: der Pin, der in **beiden** Paaren auftaucht, ist `C`. Der Partner
im Ruhezustand ist `NC`, der beim Drücken ist `NO`.

```
12:22:13   GPIO22 <-> GPIO23     Ruhe        -> 23 = C, 22 = NC
12:23:29   GPIO23 <-> GPIO4      gedrückt    -> 4  = NO
12:23:40   GPIO22 <-> GPIO23     losgelassen
```

### Fallstricke, jeder davon hat hier einmal zugeschlagen

**Pull-Defaults mitdenken.** GPIO 0–8 sind per Hardware pull-up, 9–27
pull-down. Ein `lo` auf einem pull-down-Pin ist kein Tastendruck. GPIO 2 und 3
hängen an festen 1,8-kΩ-Pull-ups der Platine und lesen *immer* `hi`.

**Nicht während des Kreuztests stichprobenartig mitlesen.** Man erwischt den
gerade getriebenen Pin und hält ihn für einen Treffer. Dreimal passiert
(GPIO6, GPIO12, GPIO27).

**GPIO14/15 aus dem Messsatz nehmen.** Das ist die UART; GPIO14 sendet selbst
und erzeugt Fehlalarme.

**Die Messung gegenprüfen, bevor man ein Ergebnis glaubt.** Einen Pin künstlich
auf Pull-down legen — meldet der Test das, funktioniert er:

```
pinctrl set 17 ip pd     # muss als Treffer erscheinen
pinctrl set 17 ip pu     # muss wieder verschwinden
```

**Ein Antippen reicht beim Kreuztest nicht.** Eine Runde über alle Pins dauert
gut eine Sekunde — gedrückt *halten*.

---

## Abnahme

`fotobox.service` neu starten und die Zeile im Log suchen:

```
hardware: Taster: trigger=GPIO27  right=GPIO22
hardware: Nicht verbaut: left — die UI blendet die zugehoerigen Aktionen aus
```

Dann `pinctrl get 22,27` — im Ruhezustand muss beides `ip pu | hi` sein,
beim Drücken fällt der jeweilige Pin auf `lo`.

Die Hauptschleife pollt mit `STATE_FPS = 8`, also alle **125 ms**, und liest
den Zustand per `is_pressed` statt per Interrupt (`main.py`). Ein sehr kurzer
Antipper kann deshalb zwischen zwei Ticks verschwinden. Für Gäste unauffällig,
beim Testen der Grund, wenn ein Druck „verschluckt" wirkt: kurz halten statt
tippen.
