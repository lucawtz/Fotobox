import { useEffect, useState, ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";
import { api } from "../../api";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "ok" | "denied">("loading");
  const location = useLocation();

  useEffect(() => {
    let alive = true;
    api.admin.me()
      .then((r) => { if (alive) setState(r.authenticated ? "ok" : "denied"); })
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
  return <>{children}</>;
}
