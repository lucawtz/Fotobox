import { Avatar } from "@mui/material";
import { AdminRole } from "../api";

/**
 * Konto-Symbol: "A" auf Blau fuer den Admin, "G" auf Lila fuer den Gastgeber.
 *
 * Eine Stelle fuer beide Header — Admin-Panel und Galerie sollen dasselbe
 * Zeichen zeigen, sonst raet man in der Galerie, was man gerade ist.
 */
export default function RoleAvatar({ role, size = 34 }: { role: AdminRole; size?: number }) {
  const isAdmin = role === "admin";
  return (
    <Avatar
      sx={{
        width: size,
        height: size,
        fontSize: ".95rem",
        bgcolor: isAdmin ? "primary.main" : "secondary.main",
        color: "primary.contrastText",
        fontWeight: 600,
      }}
    >
      {isAdmin ? "A" : "G"}
    </Avatar>
  );
}
