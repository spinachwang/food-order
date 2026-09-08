/**
 * F051 §4 — AddressPickerDialog
 *
 * 5 层级联地址选择器: 省 → 市 → 区 → 商圈 → 小区 → 门牌号.
 * 右侧实时摘要; 顶部"📍 使用当前位置"按钮触发浏览器定位.
 *
 * 行为契约:
 * - open state 由 useAddressPicker hook 管理 (ContextStrip 编辑按钮触发)
 * - 改省 → 清空市/区/商圈/小区/门牌号 (级联)
 * - 改市 → 清空区/商圈/小区/门牌号
 * - 改区 → 清空商圈/小区/门牌号
 * - Esc 关闭 / overlay click 关闭
 * - 保存: zod 校验 → usePutPreferences.mutate + chatStore.setAddress
 *
 * 不内嵌 Provider: open state 走 useAddressPicker, save 走
 * usePutPreferences mutation hook — 跟现有架构对齐, 易测.
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { CN_CITIES, findCityByName } from '../data/cn-cities'
import { useDistrictList } from '../hooks/useDistrictList'
import { usePlaceSearch } from '../hooks/usePlaceSearch'
import { useGeolocation } from '../hooks/useGeolocation'
import { useAddressPicker } from '../hooks/useAddressPicker'
import { usePutPreferences } from '../../chat/hooks/usePreferences'
import { useChatStore } from '../../../stores/chatStore'
import { structuredAddressSchema } from '../../chat/schemas'
import type { StructuredAddress } from '../../chat/types'
import { formatAddressSummary } from '../utils/formatAddressSummary'
import styles from './AddressPickerDialog.module.css'

const PLACE_TYPES_COMMUNITY = '商务住宅'

interface DraftAddress {
  province: string | null
  province_adcode: string | null
  city: string | null
  city_adcode: string | null
  district: string | null
  district_adcode: string | null
  street: string | null
  community: string | null
  poi_id: string | null
  door_no: string | null
}

function emptyDraft(): DraftAddress {
  return {
    province: null,
    province_adcode: null,
    city: null,
    city_adcode: null,
    district: null,
    district_adcode: null,
    street: null,
    community: null,
    poi_id: null,
    door_no: null,
  }
}

function draftFromCurrent(
  cur: StructuredAddress | null,
): DraftAddress {
  if (!cur) return emptyDraft()
  return { ...emptyDraft(), ...cur }
}

export function AddressPickerDialog(): JSX.Element | null {
  const { open, closeDialog } = useAddressPicker()
  const currentAddress = useChatStore((s) => s.address)
  const setAddress = useChatStore((s) => s.setAddress)
  const putPrefs = usePutPreferences()

  const [draft, setDraft] = useState<DraftAddress>(emptyDraft)
  const [validationError, setValidationError] = useState<string | null>(null)

  // dialog 打开时从 store 同步当前地址作为初始 draft
  useEffect(() => {
    if (open) {
      setDraft(draftFromCurrent(currentAddress))
      setValidationError(null)
    }
  }, [open, currentAddress])

  // ---- 级联数据 ----
  const citiesQuery = useDistrictList({
    keywords: draft.province ?? undefined,
    subdistrict: 1,
  })
  const districtsQuery = useDistrictList({
    keywords: draft.city ?? undefined,
    subdistrict: 1,
  })

  const cityList = citiesQuery.data ?? []
  const districtList = districtsQuery.data ?? []

  // 商圈 / 小区搜索 (限 city_adcode 内)
  const communitySearch = usePlaceSearch({
    keywords: draft.community ?? '',
    city: draft.city_adcode ?? undefined,
    types: PLACE_TYPES_COMMUNITY,
  })

  // ---- geolocation ----
  const geo = useGeolocation()

  // geolocation 成功 → 自动填充 city / district (跳过 province, 让用户选)
  useEffect(() => {
    if (geo.status !== 'success' || !geo.data) return
    const { province, city, district, adcode } = geo.data
    // 找省级 cache (regeo 给 province 文本 → adcode 是 city 级的 6 位)
    const matchedProvince = findCityByName(province)
    // city: 用 regeo 返回的 city 名 + 把它当市级 cache 查 adcode
    const matchedCity = findCityByName(city)
    setDraft((d) => ({
      ...d,
      province: matchedProvince?.name ?? province,
      province_adcode: matchedProvince?.adcode ?? null,
      city: matchedCity?.name ?? city,
      city_adcode: matchedCity?.adcode ?? adcode,
      district: district,
      district_adcode: adcode,
      // 商圈/小区/门牌号保留为 null — geolocation 只能定位到区
    }))
  }, [geo.status, geo.data])

  // ---- 摘要 (实时) ----
  const draftStructured: StructuredAddress | null = useMemo(() => {
    const obj: StructuredAddress = {
      province: draft.province ?? '',
      province_adcode: draft.province_adcode ?? '',
      city: draft.city ?? '',
      city_adcode: draft.city_adcode ?? '',
      district: draft.district,
      district_adcode: draft.district_adcode,
      street: draft.street,
      community: draft.community,
      poi_id: draft.poi_id,
      door_no: draft.door_no,
    }
    // 必填字段未填齐 → 当作 null (摘要为空)
    if (!obj.province || !obj.province_adcode || !obj.city || !obj.city_adcode) {
      return null
    }
    return obj
  }, [draft])

  const summary = formatAddressSummary(draftStructured)

  // ---- 级联变更 handler ----
  const onProvinceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value
    const matched = findCityByName(name)
    setDraft((d) => ({
      ...d,
      province: matched?.name ?? name,
      province_adcode: matched?.adcode ?? null,
      city: null,
      city_adcode: null,
      district: null,
      district_adcode: null,
      street: null,
      community: null,
      poi_id: null,
      door_no: d.door_no,
    }))
  }

  const onCityChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value
    // 在 cityList (省的下属) 中找匹配的 adcode
    const matched =
      cityList.find((c) => c.name === name) ?? findCityByName(name)
    setDraft((d) => ({
      ...d,
      city: matched?.name ?? name,
      city_adcode: matched?.adcode ?? null,
      district: null,
      district_adcode: null,
      street: null,
      community: null,
      poi_id: null,
      door_no: d.door_no,
    }))
  }

  const onDistrictChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value
    const matched =
      districtList.find((c) => c.name === name) ?? null
    setDraft((d) => ({
      ...d,
      district: name || null,
      district_adcode: matched?.adcode ?? null,
      street: null,
      community: null,
      poi_id: null,
      door_no: d.door_no,
    }))
  }

  const onCommunityChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDraft((d) => ({
      ...d,
      community: e.target.value || null,
      poi_id: null,
      door_no: d.door_no,
    }))
  }

  const onCommunitySelect = (
    name: string,
    poiId: string,
  ) => {
    setDraft((d) => ({
      ...d,
      community: name,
      poi_id: poiId,
    }))
  }

  const onDoorNoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDraft((d) => ({ ...d, door_no: e.target.value || null }))
  }

  // ---- 关闭: Esc 键 ----
  const dialogRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDialog()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, closeDialog])

  // ---- 保存 ----
  const onSave = async () => {
    if (!draftStructured) {
      setValidationError('请至少选到城市级 (省 / 市必填)')
      return
    }
    const parsed = structuredAddressSchema.safeParse(draftStructured)
    if (!parsed.success) {
      const firstIssue = parsed.error.issues[0]
      setValidationError(firstIssue?.message ?? '地址校验失败')
      return
    }
    setValidationError(null)
    try {
      await putPrefs.mutateAsync({
        cuisine_weights: {
          sichuan: 0.5,
          cantonese: 0.5,
          shandong: 0.5,
          suzhou: 0.5,
          zhejiang: 0.5,
          fujian: 0.5,
          hunan: 0.5,
          anhui: 0.5,
          japanese: 0.5,
          western: 0.5,
          western_fastfood: 0.5,
          chinese_fastfood: 0.5,
          snacks: 0.5,
          dessert_drinks: 0.5,
        },
        allergies: [],
        spice_tolerance: 1,
        temperature_preference: 'hot',
        default_location: parsed.data,
        budget_lunch_min: null,
        budget_lunch_max: null,
      })
      setAddress(parsed.data)
      closeDialog()
    } catch {
      // mutation 错误由 Toast 上层处理, 这里不弹
      setValidationError('保存失败,请重试')
    }
  }

  const titleId = useId()

  if (!open) return null

  return (
    <div
      className={styles.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) closeDialog()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={styles.dialog}
        data-od-id="addr-picker-dialog"
      >
        <header className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            选择地址
          </h2>
          <button
            type="button"
            className={styles.close}
            aria-label="关闭"
            data-od-id="addr-picker-close"
            onClick={closeDialog}
          >
            ✕
          </button>
        </header>

        <div className={styles.body}>
          <section className={styles.fields}>
            <button
              type="button"
              className={styles.geoButton}
              data-od-id="addr-picker-geolocate"
              onClick={geo.request}
              disabled={geo.status === 'loading'}
            >
              📍 使用当前位置
              {geo.status === 'loading' && ' · 定位中...'}
              {geo.status === 'error' && ` · ${geo.error}`}
            </button>

            <label className={styles.field}>
              <span className={styles.label}>省 / 直辖市</span>
              <select
                data-od-id="addr-picker-province"
                className={styles.input}
                value={draft.province ?? ''}
                onChange={onProvinceChange}
              >
                <option value="">请选择</option>
                {CN_CITIES.map((c) => (
                  <option key={c.adcode} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              <span className={styles.label}>市</span>
              <select
                data-od-id="addr-picker-city"
                className={styles.input}
                value={draft.city ?? ''}
                onChange={onCityChange}
                disabled={!draft.province}
              >
                <option value="">请选择</option>
                {/* 直辖市: 城市=省级, 此时 cityList 通常为空 → 显示自身 */}
                {cityList.length === 0 && draft.province && (
                  <option value={draft.province}>{draft.province}</option>
                )}
                {cityList.map((c) => (
                  <option key={c.adcode} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              <span className={styles.label}>区</span>
              <select
                data-od-id="addr-picker-district"
                className={styles.input}
                value={draft.district ?? ''}
                onChange={onDistrictChange}
                disabled={!draft.city}
              >
                <option value="">请选择</option>
                {districtList.map((c) => (
                  <option key={c.adcode} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              <span className={styles.label}>小区 / 楼宇</span>
              <input
                data-od-id="addr-picker-community"
                className={styles.input}
                type="text"
                value={draft.community ?? ''}
                onChange={onCommunityChange}
                disabled={!draft.city}
                placeholder="例如: 静安嘉里中心"
              />
              {communitySearch.data && communitySearch.data.pois.length > 0 && (
                <ul className={styles.suggest}>
                  {communitySearch.data.pois.slice(0, 5).map((p) => (
                    <li key={p.poi_id}>
                      <button
                        type="button"
                        onClick={() => onCommunitySelect(p.name, p.poi_id)}
                      >
                        {p.name} · {p.address}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </label>

            <label className={styles.field}>
              <span className={styles.label}>门牌号 / 楼层</span>
              <input
                data-od-id="addr-picker-door"
                className={styles.input}
                type="text"
                value={draft.door_no ?? ''}
                onChange={onDoorNoChange}
                placeholder="例如: B2 / 3 楼 301"
              />
            </label>

            {validationError && (
              <p className={styles.error} role="alert">
                {validationError}
              </p>
            )}
          </section>

          <aside className={styles.summary}>
            <p className={styles.summaryLabel}>实时预览</p>
            <p className={styles.summaryValue} data-od-id="addr-picker-summary">
              {summary || '— 至少选到城市级 —'}
            </p>
          </aside>
        </div>

        <footer className={styles.footer}>
          <button
            type="button"
            className={styles.cancel}
            data-od-id="addr-picker-cancel"
            onClick={closeDialog}
          >
            取消
          </button>
          <button
            type="button"
            className={styles.save}
            data-od-id="addr-picker-save"
            onClick={onSave}
          >
            保存
          </button>
        </footer>
      </div>
    </div>
  )
}
