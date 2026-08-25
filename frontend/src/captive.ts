/**
 * Captive-Portal-Popup erkennen und wieder verlassen.
 *
 * Nach dem Verbinden mit dem Hotspot oeffnet iOS automatisch den Captive
 * Network Assistant ("Captive WLAN"), Android den CaptivePortalLogin. Beides
 * sind abgespeckte WebViews: kein Share-Sheet, kein Download, kein Zugriff
 * auf die Fotos-App. Ein Tipp auf "Speichern" schliesst dort bestenfalls nur
 * das Fenster — genau das, was Gaeste als "das Bild wird nicht uebernommen"
 * melden.
 *
 * Der Ausweg fuehrt ueber /api/captive/release: danach beantwortet die Box
 * die Verbindungstests dieses Geraets mit "online", das Handy sieht das
 * Portal als erledigt an und laesst den Gast in den echten Browser wechseln
 * (Gegenstueck in gallery_server.py).
 */

/** Ueberlebt einen Reload im Popup — die URL-Markierung sehen wir nur einmal. */
const FLAG_KEY = "fotobox.captive";

/** Hat der Gast die Anmeldeseite hinter sich? Ueberlebt Reloads und die
 *  Navigation zwischen Event und Foto, damit sie nicht dauernd wiederkommt. */
const SEEN_KEY = "fotobox.captive.seen";

export function landingSeen(): boolean {
  try {
    return sessionStorage.getItem(SEEN_KEY) === "1";
  } catch {
    // Storage gesperrt (privates Fenster): dann eben jedes Mal wieder. Die
    // Anmeldeseite ist ein Hinweis, kein Zustand, an dem etwas haengt.
    return false;
  }
}

export function markLandingSeen(): void {
  try {
    sessionStorage.setItem(SEEN_KEY, "1");
  } catch {
    /* siehe landingSeen */
  }
}

/** So lange warten wir auf den echten Browser, bevor wir das Popup
 *  schliessen — und so lange steht der Zwischenschritt auf dem Schirm.
 *
 *  Frueher 1200 ms, gerade genug fuer den Sprungversuch. Der Gast bekommt in
 *  dieser Zeit aber auch die Ansage zu lesen, was gleich passiert; darunter
 *  ist die Erfolgsseite mit ihrem nackten "Success" wieder eine
 *  Ueberraschung, und genau dort sind Gaeste stehengeblieben. */
const OPEN_WAIT_MS = 2600;

const ua = (): string => navigator.userAgent || "";

export const isIOS = (): boolean =>
  /iPad|iPhone|iPod/.test(ua()) ||
  // iPadOS meldet sich seit 13 als Mac — der Touchscreen verraet das Tablet.
  (/Macintosh/.test(ua()) && navigator.maxTouchPoints > 1);

const isAndroid = (): boolean => /Android/i.test(ua());

/** Die URL, an der das Geraet seine Internet-Verbindung prueft. Unser Server
 *  faengt sie per DNS ab und antwortet nach der Freigabe mit "alles gut". */
const probeUrl = (): string =>
  isIOS()
    ? "http://captive.apple.com/hotspot-detect.html"
    : "http://connectivitycheck.gstatic.com/generate_204";

function popupUserAgent(): boolean {
  const s = ua();
  if (/iPad|iPhone|iPod/.test(s) || (/Macintosh/.test(s) && navigator.maxTouchPoints > 1)) {
    // Safari traegt "Version/17.4 … Safari/605.1.15". Eine WKWebView — und
    // das Captive-Popup ist eine — laesst diese Tokens weg. Chrome (CriOS)
    // und Firefox (FxiOS) auf iOS behalten sie und fallen hier korrekt raus.
    return !/Safari\//.test(s) || !/Version\//.test(s);
  }
  if (isAndroid()) {
    // Android-WebViews markieren sich selbst mit "; wv".
    return /;\s*wv[;)]/.test(s);
  }
  return false;
}

/** Hat der Server uns als Popup-Aufruf markiert? (302 aus einer Probe-URL) */
function readFlag(): boolean {
  let flagged = false;
  try {
    flagged = sessionStorage.getItem(FLAG_KEY) === "1";
  } catch {
    // Storage gesperrt (privates Fenster) — dann zaehlt nur die URL.
  }
  const params = new URLSearchParams(location.search);
  if (params.get("cna") !== "1") return flagged;
  try {
    sessionStorage.setItem(FLAG_KEY, "1");
  } catch {
    // s.o. — die Erkennung dieses Aufrufs steht ohnehin schon fest.
  }
  // Die Markierung gehoert nicht in eine URL, die der Gast spaeter teilt.
  params.delete("cna");
  const query = params.toString();
  history.replaceState(null, "", location.pathname + (query ? `?${query}` : "") + location.hash);
  return true;
}

let cached: boolean | null = null;

/** Laeuft die Galerie im WLAN-Anmeldefenster statt im richtigen Browser? */
export function isCaptivePopup(): boolean {
  if (cached === null) cached = readFlag() || popupUserAgent();
  return cached;
}

/** Adresse der Box zum Abtippen, falls der Sprung nicht klappt. */
export const galleryAddress = (): string => location.host;

/**
 * Freigeben und in den richtigen Browser wechseln.
 *
 * Der Sprung per x-safari-http:// bzw. intent:// ist der bequeme Weg. Gibt es
 * ihn nicht, faellt das still ins Leere — deshalb danach die Probe-URL: das
 * OS liest sie als "Anmeldung erledigt", schliesst das Popup und behaelt das
 * WLAN, statt es beim naechsten Test als tot zu verwerfen.
 *
 * `onWaiting` wird aufgerufen, sobald die Freigabe durch ist und die Seite
 * gleich verlassen wird. Der Aufrufer blendet damit die Ansage ein, was als
 * Naechstes passiert (CaptiveNotice). Klappt der Sprung in den echten
 * Browser, sieht der Gast sie nie — dann ist er schon weg.
 */
export async function leaveCaptivePopup(
  onWaiting?: () => void,
): Promise<void> {
  const target = `${location.origin}/`;
  try {
    await fetch("/api/captive/release", { method: "POST", cache: "no-store" });
  } catch {
    // Freigabe nicht durchgekommen: dann bleibt das Popup eben offen. Der
    // Sprung in den echten Browser ist trotzdem einen Versuch wert.
  }

  onWaiting?.();

  const deep = isIOS()
    ? target.replace(/^http:/, "x-safari-http:")
    : isAndroid()
      // intent:// traegt seine Fallback-URL selbst — Chrome springt dorthin,
      // wenn das Schema nirgends ankommt.
      ? `intent://${location.host}/#Intent;scheme=http;` +
        `S.browser_fallback_url=${encodeURIComponent(target)};end`
      : "";

  // Auch ohne Sprungziel wird gewartet: die Ansage soll gelesen werden
  // koennen, bevor die Erfolgsseite kommt.
  window.setTimeout(() => {
    // Seite im Hintergrund = der echte Browser ist aufgegangen. Dann hier
    // nichts mehr anfassen, sonst steht der Gast wieder im Popup.
    if (document.hidden) return;
    location.href = probeUrl();
  }, OPEN_WAIT_MS);
  if (deep) location.href = deep;
}
