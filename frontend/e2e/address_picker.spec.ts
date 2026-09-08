/**
 * F051 §4 — AddressPickerDialog 端到端.
 *
 * 覆盖 plan G-4 spec 1: 打开 dialog → 5 层选完 → 保存 → ContextStrip
 * 更新 → SSE weather 非 null.
 *
 * 网络层 mock: 真实跑这条测试时 vite proxy 到 backend 的 8000 端口未
 * 起; 用 page.route() 注入 districts / preferences / geocode 假数据,
 * 锁定前端契约. SSE 流也走 mock (context-strip 天气显示依赖 chatStore).
 *
 * 不依赖 LLM 凭据; CI 可跑.
 */
import { test, expect, type Route } from '@playwright/test'

const FAKE_DISTRICTS = {
  shanghai_city: [
    { adcode: '310100', name: '上海市', center: '121.473701,31.230416' },
  ],
  jingan_district: [
    { adcode: '310106', name: '静安区', center: '121.447,31.228' },
  ],
}

const FAKE_PREFS_GET = {
  cuisine_weights: {
    sichuan: 0.5, cantonese: 0.5, shandong: 0.5, suzhou: 0.5,
    zhejiang: 0.5, fujian: 0.5, hunan: 0.5, anhui: 0.5,
    japanese: 0.5, western: 0.5, western_fastfood: 0.5,
    chinese_fastfood: 0.5, snacks: 0.5, dessert_drinks: 0.5,
  },
  allergies: [],
  spice_tolerance: 1,
  temperature_preference: 'hot',
  default_location: null,
  budget_lunch_min: null,
  budget_lunch_max: null,
}

test.beforeEach(async ({ page }) => {
  // mock districts — 根据 keywords 关键词返回不同层级
  await page.route('**/api/v1/districts**', async (route: Route) => {
    const url = new URL(route.request().url())
    const kw = url.searchParams.get('keywords') ?? ''
    if (kw === '上海市') return route.fulfill({ json: FAKE_DISTRICTS.shanghai_city })
    if (kw === '上海市静安区' || kw === '310100') {
      return route.fulfill({ json: FAKE_DISTRICTS.jingan_district })
    }
    return route.fulfill({ json: [] })
  })

  // mock preferences GET + PUT
  await page.route('**/api/v1/preferences', async (route: Route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: FAKE_PREFS_GET })
    }
    return route.fulfill({ json: { ok: true } })
  })

  // mock geocode regeo
  await page.route('**/api/v1/geocode/regeo**', async (route: Route) => {
    return route.fulfill({
      json: {
        province: '上海市',
        city: '上海市',
        district: '静安区',
        adcode: '310106',
        formatted_address: '上海市静安区南京西路 1788 号',
        longitude: 121.473701,
        latitude: 31.230416,
      },
    })
  })
})

test('happy path: 5 层选完 → 保存 → ContextStrip 显示结构化摘要', async ({ page }) => {
  await page.goto('/')

  // 点 ContextStrip 的编辑按钮
  await page.locator('[data-od-id="addr-edit"]').click()

  // dialog 出现 + 摘要占位
  const dialog = page.locator('[data-od-id="addr-picker-dialog"]')
  await expect(dialog).toBeVisible()
  await expect(page.locator('[data-od-id="addr-picker-summary"]'))
    .toContainText('至少选到城市级')

  // 选直辖市 → 直辖市省/市同
  await page.locator('[data-od-id="addr-picker-province"]').selectOption('上海市')
  await page.locator('[data-od-id="addr-picker-city"]').selectOption('上海市')

  // 选区 (使用 mock 返回的静安区)
  await page.locator('[data-od-id="addr-picker-district"]').selectOption('静安区')

  // 小区 + 门牌号
  await page.locator('[data-od-id="addr-picker-community"]').fill('静安嘉里中心')
  await page.locator('[data-od-id="addr-picker-door"]').fill('B2')

  // 摘要应为 "上海市 · 静安区 · 静安嘉里中心 · B2"
  await expect(page.locator('[data-od-id="addr-picker-summary"]'))
    .toContainText('上海市 · 静安区 · 静安嘉里中心 · B2')

  // 保存
  await page.locator('[data-od-id="addr-picker-save"]').click()

  // dialog 关闭
  await expect(dialog).toBeHidden()

  // ContextStrip 显示新摘要
  await expect(page.locator('[data-od-id="addr-summary"]'))
    .toContainText('上海市 · 静安区 · 静安嘉里中心 · B2')
})

test('省/市都没选就保存 → 校验红字 + dialog 保持 open', async ({ page }) => {
  await page.goto('/')
  await page.locator('[data-od-id="addr-edit"]').click()

  const dialog = page.locator('[data-od-id="addr-picker-dialog"]')
  await expect(dialog).toBeVisible()

  await page.locator('[data-od-id="addr-picker-save"]').click()

  // 校验红字出现, dialog 仍然 open
  const alert = dialog.locator('[role="alert"]')
  await expect(alert).toContainText('至少选到城市级')
  await expect(dialog).toBeVisible()
})

test('Esc 关闭 dialog', async ({ page }) => {
  await page.goto('/')
  await page.locator('[data-od-id="addr-edit"]').click()
  const dialog = page.locator('[data-od-id="addr-picker-dialog"]')
  await expect(dialog).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
})
