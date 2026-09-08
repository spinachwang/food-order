/**
 * F051 §6.2 — Legacy 字符串兼容路径.
 *
 * 覆盖 plan G-4 spec 3: 后端 default_location 仍存老字符串 (DB 迁移前
 * 状态) → GET preferences 返回 default_location === null (后端 schema
 * 拒绝解析, 落到 null) → 前端 dialog 仍可正常打开, 用户重新选新区 → 保存成功.
 *
 * 注: 这个 spec 验证**前端容错路径** — DB 实际上 alembic 迁移后所有 row
 * 都应该是 JSON; 这里只模拟历史 row 或上游 bug.
 */
import { test, expect, type Route } from '@playwright/test'

const FAKE_DISTRICTS = {
  beijing: [
    { adcode: '110100', name: '北京市', center: '116.4074,39.9042' },
  ],
  chaoyang: [
    { adcode: '110105', name: '朝阳区', center: '116.4828,39.9214' },
  ],
}

/** 模拟 DB 老字符串 — 后端 GET 时落到 default_location: null */
const FAKE_PREFS_GET_LEGACY_NULL = {
  cuisine_weights: {
    sichuan: 0.5, cantonese: 0.5, shandong: 0.5, suzhou: 0.5,
    zhejiang: 0.5, fujian: 0.5, hunan: 0.5, anhui: 0.5,
    japanese: 0.5, western: 0.5, western_fastfood: 0.5,
    chinese_fastfood: 0.5, snacks: 0.5, dessert_drinks: 0.5,
  },
  allergies: [],
  spice_tolerance: 1,
  temperature_preference: 'hot',
  default_location: null, // 兼容路径下后端 schema 拒绝解析老字符串
  budget_lunch_min: null,
  budget_lunch_max: null,
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/districts**', async (route: Route) => {
    const url = new URL(route.request().url())
    const kw = url.searchParams.get('keywords') ?? ''
    if (kw === '北京市') return route.fulfill({ json: FAKE_DISTRICTS.beijing })
    if (kw === '110100') return route.fulfill({ json: FAKE_DISTRICTS.chaoyang })
    return route.fulfill({ json: [] })
  })

  await page.route('**/api/v1/preferences', async (route: Route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: FAKE_PREFS_GET_LEGACY_NULL })
    }
    // PUT 也接受 — 用户保存新区
    return route.fulfill({ json: { ok: true } })
  })
})

test('default_location=null (兼容路径) → ContextStrip 显示兜底 → 可重选 → 保存', async ({ page }) => {
  await page.goto('/')

  // 兼容路径: address 兜底字符串 (ContextStrip §6.5)
  await expect(page.locator('[data-od-id="addr-summary"]'))
    .toContainText('上海 · 静安嘉里中心 B2')

  // 打开 dialog — 字段都为空 (从 store 同步空 draft)
  await page.locator('[data-od-id="addr-edit"]').click()
  const dialog = page.locator('[data-od-id="addr-picker-dialog"]')
  await expect(dialog).toBeVisible()

  // 选北京 → 朝阳区
  await page.locator('[data-od-id="addr-picker-province"]').selectOption('北京市')
  await page.locator('[data-od-id="addr-picker-city"]').selectOption('北京市')
  await page.locator('[data-od-id="addr-picker-district"]').selectOption('朝阳区')

  await page.locator('[data-od-id="addr-picker-door"]').fill('国贸三期 26F')

  // 摘要同步
  await expect(page.locator('[data-od-id="addr-picker-summary"]'))
    .toContainText('北京市 · 朝阳区 · 国贸三期 26F')

  // 保存
  await page.locator('[data-od-id="addr-picker-save"]').click()
  await expect(dialog).toBeHidden()

  // ContextStrip 更新为结构化摘要
  await expect(page.locator('[data-od-id="addr-summary"]'))
    .toContainText('北京市 · 朝阳区 · 国贸三期 26F')
})
