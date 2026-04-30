import { Routes, Route, Navigate } from "react-router-dom";
import Gallery from "./pages/Gallery";
import PhotoView from "./pages/PhotoView";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Gallery />} />
      <Route path="/photo/:filename" element={<PhotoView />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
