import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// This config file is loaded as ESM (package.json has "type": "module"),
// where __dirname doesn't exist — resolve paths from import.meta.url instead.
const root = fileURLToPath(new URL(".", import.meta.url));

// Two independent entry points: the side panel document (a normal HTML+JS
// page) and the background service worker (Chrome loads
// manifest.background.service_worker as a fixed path, so it must not be
// code-split or hashed).
export default defineConfig({
  // Root-relative ("/sidepanel.js") asset paths break once this HTML file
  // is loaded as chrome-extension://<id>/dist/sidepanel.html — "/" would
  // resolve to the extension root, not this file's own directory. Relative
  // paths resolve correctly regardless of which directory the manifest
  // points at.
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        sidepanel: `${root}sidepanel.html`,
        background: `${root}background.ts`,
      },
      output: {
        entryFileNames: "[name].js",
      },
    },
  },
});
