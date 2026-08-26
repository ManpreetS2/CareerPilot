// Reuses ../frontend/tailwind.config.js's theme (a plain JS object import,
// not a build-graph dependency) so the panel matches the main web app's
// look exactly. content/darkMode are separate since this is its own
// package with its own source tree.
import frontendConfig from "../frontend/tailwind.config.js";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./sidepanel.html", "./src/**/*.{js,ts}"],
  darkMode: "class",
  theme: frontendConfig.theme,
  plugins: [],
};
