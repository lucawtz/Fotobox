import { useEffect, useState, ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";
import { api, AdminRole } from "../../api";
import { AuthContext } from "./authContext";

interface Props {
  children: ReactNode;
  requireAdmin?: boolean;
}

export default function RequireAuth({ children, requireAdmin }: Props) {
  const [state, setState] = useState<"loading" | "denied" | { role: AdminRole }>("loading");
  const location = useLocation();

  useEffect(() => {
    let alive = true;
    api.admin.me()
      .then((r) => {
        if (!alive) return;
        if (r.authenticated && r.role) setState({ role: r.role });
        else setState("denied");
      })
      .catch(() => { if (alive) setState("denied"); });
    return () => { alive = false; };
  }, []);

  if (state === "loading") {
    return (
      <Box sx={{ minHeight: "100dvh", display: "grid", placeItems: "center" }}>
        <CircularProgress sx={{ color: "primary.light" }} />
      </Box>
    );
  }
  if (state === "denied") {
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;
  }
  // Eingeloggt aber falsche Rolle → zurück auf die Übersicht (Gastgeber darf
  // sie sehen, also kein Login-Loop).
  if (requireAdmin && state.role !== "admin") {
    return <Navigate to="/admin" replace />;
  }
  return (
    <AuthContext.Provider value={{ role: state.role }}>
      {children}
    </AuthContext.Provider>
  );
}
