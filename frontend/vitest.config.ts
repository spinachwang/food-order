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
    // F051 §G-5: 80% 覆盖率门槛 — 不下调, 不达标先补单测
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        // 类型声明 / 入口 / 配置文件 — 不计入覆盖率
        'src/**/*.d.ts',
        'src/main.tsx',
        'src/test-setup.ts',
        'src/types/**',
        // CSS Modules 不测覆盖率
        'src/**/*.module.css',
      ],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
      },
    },
  },
})