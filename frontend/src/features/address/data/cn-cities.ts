/**
 * F051 §2.1 #6 — 中国行政区划硬编码缓存.
 *
 * 两个并列常量:
 * 1. `CN_PROVINCES` — 34 个省级单位 (省 / 直辖市 / 自治区 / 特别行政区).
 *    用于 AddressPickerDialog 的「省 / 直辖市」下拉首屏选项.
 *
 * 2. `CN_CITY_CACHE` — 36 个常用市级单位 (4 直辖市 + 27 省会 + 5 计划单列市).
 *    用于 regeo 回调把 city 文本 → 市级 adcode.
 *    regeo 返回的 `city` 字段对直辖市是「北京市」(同 province),
 *    对省会是「杭州市」; 都需要在常用市级 cache 里查市级 adcode.
 *
 * 早期版本混在一个 36 项数组里, 触发 F051 §4 bug: 用户在「省」select
 * 实际选到了「杭州市」(330100 市级 adcode), 级联全错位. 2026-09-08
 * 拆成省级 + 市级两个独立常量, 各自语义清晰.
 *
 * adcode 来源: GB/T 2260 + 高德 /config/district 公开响应快照 (2026-09).
 */

export interface CnCityEntry {
  /** 中文显示名 — 与高德 district.name 完全一致 */
  name: string
  /** 6 位数字 adcode — 省级 (末 4 位 0000) 或市级 (末 4 位非 0000) */
  adcode: string
}

// =====================================================================
// 1. 省级单位 — AddressPickerDialog 省级 select 专用
// =====================================================================

export const CN_PROVINCES: readonly CnCityEntry[] = [
  // ---- 4 直辖市 ----
  { name: '北京市', adcode: '110000' },
  { name: '天津市', adcode: '120000' },
  { name: '上海市', adcode: '310000' },
  { name: '重庆市', adcode: '500000' },
  // ---- 23 省 (按拼音首字母排序) ----
  { name: '河北省', adcode: '130000' },
  { name: '山西省', adcode: '140000' },
  { name: '辽宁省', adcode: '210000' },
  { name: '吉林省', adcode: '220000' },
  { name: '黑龙江省', adcode: '230000' },
  { name: '江苏省', adcode: '320000' },
  { name: '浙江省', adcode: '330000' },
  { name: '安徽省', adcode: '340000' },
  { name: '福建省', adcode: '350000' },
  { name: '江西省', adcode: '360000' },
  { name: '山东省', adcode: '370000' },
  { name: '河南省', adcode: '410000' },
  { name: '湖北省', adcode: '420000' },
  { name: '湖南省', adcode: '430000' },
  { name: '广东省', adcode: '440000' },
  { name: '海南省', adcode: '460000' },
  { name: '四川省', adcode: '510000' },
  { name: '贵州省', adcode: '520000' },
  { name: '云南省', adcode: '530000' },
  { name: '陕西省', adcode: '610000' },
  { name: '甘肃省', adcode: '620000' },
  { name: '青海省', adcode: '630000' },
  { name: '台湾省', adcode: '710000' },
  // ---- 5 自治区 ----
  { name: '内蒙古自治区', adcode: '150000' },
  { name: '广西壮族自治区', adcode: '450000' },
  { name: '西藏自治区', adcode: '540000' },
  { name: '宁夏回族自治区', adcode: '640000' },
  { name: '新疆维吾尔自治区', adcode: '650000' },
  // ---- 2 特别行政区 ----
  { name: '香港特别行政区', adcode: '810000' },
  { name: '澳门特别行政区', adcode: '820000' },
] as const

/** 省级: 按 name 查询. AddressPickerDialog 省级 select 用. */
export function findProvinceByName(name: string): CnCityEntry | undefined {
  return CN_PROVINCES.find((c) => c.name === name)
}

/** 省级: 按 adcode 查询. regeo 回调时根据省级 adcode 自动选回省级. */
export function findProvinceByAdcode(adcode: string): CnCityEntry | undefined {
  return CN_PROVINCES.find((c) => c.adcode === adcode)
}

// =====================================================================
// 2. 市级 cache — regeo 回调把 city 文本转市级 adcode 用
// =====================================================================

export const CN_CITY_CACHE: readonly CnCityEntry[] = [
  // ---- 4 直辖市 ----
  // 直辖市的市级 adcode 与省级同 (110000 / 120000 / 310000 / 500000)
  { name: '北京市', adcode: '110000' },
  { name: '天津市', adcode: '120000' },
  { name: '上海市', adcode: '310000' },
  { name: '重庆市', adcode: '500000' },
  // ---- 27 省会 / 自治区首府 (按拼音首字母排序) ----
  { name: '石家庄市', adcode: '130100' },
  { name: '太原市', adcode: '140100' },
  { name: '呼和浩特市', adcode: '150100' },
  { name: '沈阳市', adcode: '210100' },
  { name: '长春市', adcode: '220100' },
  { name: '哈尔滨市', adcode: '230100' },
  { name: '南京市', adcode: '320100' },
  { name: '杭州市', adcode: '330100' },
  { name: '合肥市', adcode: '340100' },
  { name: '福州市', adcode: '350100' },
  { name: '南昌市', adcode: '360100' },
  { name: '济南市', adcode: '370100' },
  { name: '郑州市', adcode: '410100' },
  { name: '武汉市', adcode: '420100' },
  { name: '长沙市', adcode: '430100' },
  { name: '广州市', adcode: '440100' },
  { name: '南宁市', adcode: '450100' },
  { name: '海口市', adcode: '460100' },
  { name: '成都市', adcode: '510100' },
  { name: '贵阳市', adcode: '520100' },
  { name: '昆明市', adcode: '530100' },
  { name: '拉萨市', adcode: '540100' },
  { name: '西安市', adcode: '610100' },
  { name: '兰州市', adcode: '620100' },
  { name: '西宁市', adcode: '630100' },
  { name: '银川市', adcode: '640100' },
  { name: '乌鲁木齐市', adcode: '650100' },
  // ---- 5 计划单列市 ----
  { name: '大连市', adcode: '210200' },
  { name: '青岛市', adcode: '370200' },
  { name: '宁波市', adcode: '330200' },
  { name: '厦门市', adcode: '350200' },
  { name: '深圳市', adcode: '440300' },
] as const

/** 市级: 按 name 查询 — regeo 回调拿市级 adcode. */
export function findCityInCacheByName(name: string): CnCityEntry | undefined {
  return CN_CITY_CACHE.find((c) => c.name === name)
}

/** 市级: 按 adcode 查询. */
export function findCityInCacheByAdcode(adcode: string): CnCityEntry | undefined {
  return CN_CITY_CACHE.find((c) => c.adcode === adcode)
}