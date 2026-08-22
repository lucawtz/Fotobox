import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, CssBaseline } from "@mui/material";
// Inter selbst hosten statt von fonts.googleapis.com: der Fotobox-Hotspot
// hat kein Internet, und dnsmasq leitet alle DNS-Anfragen auf den Pi um —
// das "Stylesheet" von Google waere in Wahrheit ein 302 auf die Galerie.
// wght.css bringt alle Subsets mit unicode-range mit, das Handy laedt nur Latin.
import "@fontsource-variable/inter/wght.css";
import theme from "./theme";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
);
