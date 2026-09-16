import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import { PointerDemo } from "./PointerDemo.jsx";
import { CameraGaze } from "./CameraGaze.jsx";
import "./styles.css";
import "./demo.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
    <PointerDemo />
    <CameraGaze />
  </React.StrictMode>,
);
