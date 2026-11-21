import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on the LAN too, so the web app can be opened from a phone on the
    // same Wi-Fi during development.
    host: true,
  },
})
