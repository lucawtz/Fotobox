import { Routes, Route, Navigate } from "react-router-dom";
import Gallery from "./pages/Gallery";
import PhotoView from "./pages/PhotoView";
import AdminLogin from "./pages/admin/AdminLogin";
import AdminLayout from "./pages/admin/AdminLayout";
import AdminOverview from "./pages/admin/AdminOverview";
import AdminEvent from "./pages/admin/AdminEvent";
import AdminWifi from "./pages/admin/AdminWifi";
import AdminBranding from "./pages/admin/AdminBranding";
import AdminMaintenance from "./pages/admin/AdminMaintenance";
import RequireAuth from "./pages/admin/RequireAuth";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Gallery />} />
      <Route path="/photo/:filename" element={<PhotoView />} />

      <Route path="/admin/login" element={<AdminLogin />} />
      <Route
        path="/admin"
        element={
          <RequireAuth>
            <AdminLayout />
          </RequireAuth>
        }
      >
        <Route index element={<AdminOverview />} />
        <Route path="event"       element={<AdminEvent />} />
        <Route path="wifi"        element={<AdminWifi />} />
        <Route path="branding"    element={<AdminBranding />} />
        <Route path="maintenance" element={<AdminMaintenance />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
