import { resolve } from "node:path";
import { defineConfig } from "vite";

// Deux pages, comme les deux gabarits Flask : accueil (index.html) et page de partage (view.html).
export default defineConfig({
  root: __dirname,
  publicDir: false,
  server: { fs: { allow: [resolve(__dirname, "..")] } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, "index.html"),
        view: resolve(__dirname, "view.html"),
      },
    },
  },
});
