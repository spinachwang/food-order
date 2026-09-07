/**
 * F050 E2E — 主页基本结构
 *
 * 假设 backend dev server 不在跑, 前端独立验证:
 * - TopBar 渲染
 * - Hero 渲染
 * - PreferencesPanel 渲染
 * - RecommendationCard 占位态渲染
 * - Footer 渲染
 *
 * 不依赖 SSE; 真实流走 chat_flow 集成测试覆盖.
 */
import { test, expect } from '@playwright/test'

test('homepage 基本结构', async ({ page }) => {
  await page.goto('/')

  // TopBar
  await expect(page.getByText('午饭吃什么')).toBeVisible()
  await expect(page.getByLabel('用户头像 Z')).toBeVisible()

  // Hero
  await expect(page.getByRole('heading', { level: 1 })).toContainText('今天中午')

  // ContextStrip
  await expect(page.getByText(/天气/)).toBeVisible()

  // PreferencesPanel
  await expect(page.locator('[data-od-id="prefs-panel"]')).toBeVisible()
  await expect(page.locator('[data-od-id="ask-agent"]')).toBeVisible()

  // RecommendationCard 占位态
  await expect(page.locator('[data-od-id="reco-main-empty"]')).toBeVisible()

  // ThinkingLog
  await expect(page.locator('[data-od-id="thinking-log"]')).toBeVisible()

  // Footer
  await expect(page.getByText(/数据: 高德 POI/)).toBeVisible()
})

test('点 chip 川菜 → aria-pressed=true', async ({ page }) => {
  await page.goto('/')
  await page.waitForSelector('[data-od-id="chip-sichuan"]')
  const chip = page.locator('[data-od-id="chip-sichuan"]')
  await expect(chip).toHaveAttribute('aria-pressed', 'false')
  await chip.click()
  await expect(chip).toHaveAttribute('aria-pressed', 'true')
})

test('reset-prefs 恢复默认', async ({ page }) => {
  await page.goto('/')
  await page.waitForSelector('[data-od-id="chip-sichuan"]')
  await page.locator('[data-od-id="chip-sichuan"]').click()
  await expect(page.locator('[data-od-id="prefs-count"]')).toContainText('1')
  await page.locator('[data-od-id="reset-prefs"]').click()
  await expect(page.locator('[data-od-id="prefs-count"]')).toContainText('0')
})

test('preset-rainy 不发 PUT,仅本地', async ({ page }) => {
  await page.goto('/')
  await page.waitForSelector('[data-od-id="preset-rainy"]')
  // 不监听 fetch; 点 rainy → mood 切换
  await page.locator('[data-od-id="preset-rainy"]').click()
  await expect(page.locator('[data-od-id="mood-want-comfort"]')).toHaveAttribute('aria-checked', 'true')
})

test('天气占位文案', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('天气暂不可用')).toBeVisible()
})

test('响应式: <1080px 切换 reco-wrap 为单列', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 900 })
  await page.goto('/')
  // reco-wrap 在 800px 应为单列 (由 ChatShell.module.css 控制)
  const wrap = page.locator('[data-od-id="reco-wrap"]')
  await expect(wrap).toBeVisible()
})

test('响应式: <720px 隐藏 TopBar 导航', async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 900 })
  await page.goto('/')
  await expect(page.getByText('午饭吃什么')).toBeVisible()
  // 导航链接应隐藏
  await expect(page.locator('nav')).toBeHidden()
})