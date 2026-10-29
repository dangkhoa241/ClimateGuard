import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Screen render tests only (the other tests use node:test, see package.json "test").
export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', include: ['src/**/*.screens.test.jsx'] },
})
