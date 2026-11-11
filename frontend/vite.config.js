import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import tailwindcss from '@tailwindcss/vite'

// L'interface compilée est servie par FastAPI depuis app/static
export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  build: { outDir: '../app/static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8098' } },
})
