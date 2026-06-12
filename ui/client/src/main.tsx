import { createRoot } from "react-dom/client";
import App from "./App";
import { installFadingScrollbars } from "./lib/fading-scrollbars";
import "./index.css";

installFadingScrollbars();

createRoot(document.getElementById("root")!).render(<App />);
