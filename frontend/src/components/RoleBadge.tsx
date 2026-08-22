import { IconButton, Tooltip } from "@mui/material";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import RoleAvatar from "./RoleAvatar";
import { useSessionRole } from "../sessionRole";

const LABEL = { admin: "Admin", host: "Gastgeber" } as const;

interface Props {
  /** Im Gast-Zustand gar nichts zeigen — fuer Header, die bisher keinen
   *  Admin-Einstieg hatten und fuer Gaeste unveraendert bleiben sollen. */
  hideWhenGuest?: boolean;
}

/**
 * Zeigt im Galerie-Header, mit welcher Rolle man unterwegs ist — mit genau dem
 * Konto-Symbol aus dem Admin-Panel (RoleAvatar) — und fuehrt mit einem Tipp
 * dorthin.
 *
 * Als Gast bleibt es beim schlichten Schild-Icon wie bisher: fuer diesen
 * Zustand gibt es in /admin kein Gegenstueck, und ein "Gast"-Zeichen im Header
 * jedes Partygasts sagt niemandem etwas.
 *
 * Solange die Rolle noch nicht feststeht (`undefined`), wird der Gast-Zustand
 * gezeigt: das ist der haeufigste Fall, und so springt der Header nicht bei
 * jedem Galerie-Aufruf.
 */
export default function RoleBadge({ hideWhenGuest = false }: Props) {
  const role = useSessionRole();
  const goAdmin = () => { window.location.href = "/admin"; };

  if (role !== "admin" && role !== "host") {
    if (hideWhenGuest) return null;
    return (
      <Tooltip title="Nicht angemeldet — zum Anmelden tippen">
        <IconButton onClick={goAdmin} size="medium" aria-label="Anmelden">
          <AdminPanelSettingsRoundedIcon />
        </IconButton>
      </Tooltip>
    );
  }

  return (
    <Tooltip title={`Angemeldet als ${LABEL[role]} — zum Admin-Panel tippen`}>
      <IconButton
        onClick={goAdmin}
        sx={{ p: 0.5, flexShrink: 0 }}
        aria-label={`Angemeldet als ${LABEL[role]}`}
      >
        <RoleAvatar role={role} />
      </IconButton>
    </Tooltip>
  );
}
