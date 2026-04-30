import { createContext, useContext } from "react";
import { AdminRole } from "../../api";

export interface AuthState {
  role: AdminRole;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth außerhalb von <RequireAuth>");
  return ctx;
}
