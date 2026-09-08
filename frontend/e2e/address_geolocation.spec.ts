/**
 * F051 §4 — "使用当前位置" 端到端.
 *
 * 覆盖 plan G-4 spec 2: Playwright mock navigator.geolocation →
 * AddressPickerDialog 触发 geolocation → regeo mock → 自动填 city/district.
 *
 * Playwright 的 context.setGeolocation + grantPermissions 是官方支持
 * 的 mock 途径, 不需要在 page.evaluate 里 stub navigator.
 */
import { test, expect, type Route } from '@playwright/test'

const FAKE_DISTRICTS = {
  shanghai: [{ adcode: '310100', name: '上海市', center: '121.473701,31.230416' }],
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

test.beforeEach(async ({ page, context }) => {
  // 授权 geolocation + 注入坐标 (上海市静安区)
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ longitude: 121.473701, latitude: 31.230416 })

  await page.route('**/api/v1/districts**', async (route: Route) => {
    const url = new URL(route.request().url())
    const kw = url.searchParams.get('keywords') ?? ''
    if (kw === '上海市') return route.fulfill({ json: FAKE_DISTRICTS.shanghai })
    return route.fulfill({ json: [] })
  })

  await page.route('**/api/v1/preferences', async (route: Route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: FAKE_PREFS_GET })
    }
    return route.fulfill({ json: { ok: true } })
  })

  await page.route('**/api/v1/geocode/regeo**', async (route: Route) => {
    return route.fulfill({
      json: {
        province: '上海市',
        city: '上海市',
        district: '静安区',
        adcode: '310106',
        formatted_address: '上海市静安区南京西路',
        longitude: 121.473701,
        latitude: 31.230416,
      },
    })
  })
})

test('点 "使用当前位置" → 自动填 city + district', async ({ page }) => {
  await page.goto('/')
  await page.locator('[data-od-id="addr-edit"]').click()

  const dialog = page.locator('[data-od-id="addr-picker-dialog"]')
  await expect(dialog).toBeVisible()

  // 触发定位
  const geoBtn = page.locator('[data-od-id="addr-picker-geolocate"]')
  await geoBtn.click()

  // 摘要应反映 city + district (geolocation 只填到区级)
  const summary = page.locator('[data-od-id="addr-picker-summary"]')
  await expect(summary).toContainText('上海市 · 静安区', { timeout: 5_000 })

  // province select 也应被回填
  const provinceValue = await page.locator('[data-od-id="addr-picker-province"]').inputValue()
  expect(provinceValue).toBe('上海市')
})
