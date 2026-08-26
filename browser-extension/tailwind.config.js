// Reuses ../frontend/tailwind.config.js's theme (a plain JS object import,
// not a build-graph dependency) so the panel matches the main web app's
// look exactly. content/darkMode are separate since this is its own
// package with its own source tree.
import frontendConfig from "../frontend/tailwind.config.js";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./sidepanel.html", "./src/**/*.{js,ts}"],
  // "media", not the web app's "class". The web app toggles a .dark class
  // from a stored preference; the panel has no theme switcher and cannot
  // read that preference anyway (it lives in the web app origin's
  // localStorage, which an extension page can't touch). Setting the class
  // from JS would also need an inline <script> in <head> to avoid a
  // light-mode flash, and MV3's extension CSP forbids inline scripts. Going
  // by prefers-color-scheme resolves in pure CSS before first paint.
  darkMode: "media",
  theme: frontendConfig.theme,
  plugins: [],
};
