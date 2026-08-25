import { lazy, Suspense, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Gallery from "./pages/Gallery";
import EventGallery from "./pages/EventGallery";
import PhotoView from "./pages/PhotoView";
import { CaptiveLanding, captiveLandingPending } from "./components/CaptiveNotice";

// Admin-Pages lazy laden — Gäste brauchen den Code nie, also nicht in den
// Gallery-Bundle reinmischen. Spart ~300 KB+ beim ersten Galerie-Aufruf.
const AdminLogin       = lazy(() => import("./pages/admin/AdminLogin"));
const AdminLayout      = lazy(() => import("./pages/admin/AdminLayout"));
const AdminOverview    = lazy(() => import("./pages/admin/AdminOverview"));
const AdminEvent       = lazy(() => import("./pages/admin/AdminEvent"));
const AdminWifi        = lazy(() => import("./pages/admin/AdminWifi"));
const AdminBranding    = lazy(() => import("./pages/admin/AdminBranding"));
const AdminPrint       = lazy(() => import("./pages/admin/AdminPrint"));
const AdminMaintenance = lazy(() => import("./pages/admin/AdminMaintenance"));
const RequireAuth      = lazy(() => import("./pages/admin/RequireAuth"));

export default function App() {
  // Vor allen Routen, nicht in der Galerie: das Fenster kann auch direkt auf
  // einem Event oder einem einzelnen Foto aufgehen, und die Anmeldung steht
  // dann genauso an.
  const [landing, setLanding] = useState(captiveLandingPending);
  if (landing) return <CaptiveLanding onSkip={() => setLanding(false)} />;
  return (
    <Routes>
      <Route path="/" element={<Gallery />} />
      <Route path="/event/:folder" element={<EventGallery />} />
      <Route path="/photo/:event/:filename" element={<PhotoView />} />

      <Route
        path="/admin/login"
        element={
          <Suspense fallback={null}>
            <AdminLogin />
          </Suspense>
        }
      />
      <Route
        path="/admin"
        element={
          <Suspense fallback={null}>
            <RequireAuth>
              <AdminLayout />
            </RequireAuth>
          </Suspense>
        }
      >
        <Route index            element={<Suspense fallback={null}><AdminOverview /></Suspense>} />
        <Route path="event"     element={<Suspense fallback={null}><AdminEvent /></Suspense>} />
        <Route path="branding"  element={<Suspense fallback={null}><AdminBranding /></Suspense>} />
        <Route path="wifi"      element={<Suspense fallback={null}><AdminWifi /></Suspense>} />
        <Route
          path="print"
          element={
            <Suspense fallback={null}>
              <RequireAuth requireAdmin>
                <AdminPrint />
              </RequireAuth>
            </Suspense>
          }
        />
        <Route
          path="maintenance"
          element={
            <Suspense fallback={null}>
              <RequireAuth requireAdmin>
                <AdminMaintenance />
              </RequireAuth>
            </Suspense>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
