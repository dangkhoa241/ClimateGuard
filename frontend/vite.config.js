import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { stampServiceWorkerPlugin } from './scripts/stamp-sw.mjs'

export default defineConfig({
  plugins: [react(), stampServiceWorkerPlugin()],
})
