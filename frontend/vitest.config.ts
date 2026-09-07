/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // F050: E2E (Playwright) 走 .spec.ts, 不归 Vitest 管
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
  },
})