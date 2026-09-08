/**
 * F051 §2.1 #6 — 36 项硬编码中国主要城市缓存.
 *
 * 用途: AddressPickerDialog 首屏打开时不发请求, 直接展示「省级 / 直辖市 /
 * 省会 / 计划单列市」下拉. 用户聚焦城市下拉时, 后续调用 useDistrictList
 * 拉权威高德数据覆盖 (此 cache 只是首屏兜底).
 *
 * 来源:
 * - 4 直辖市: 北京 / 上海 / 天津 / 重庆
 * - 27 省会 (含 5 自治区首府): 哈尔滨 / 长春 / 沈阳 / 呼和浩特 / 乌鲁木齐 /
 *   兰州 / 西宁 / 西安 / 银川 / 郑州 / 济南 / 太原 / 合肥 / 武汉 / 长沙 /
 *   南京 / 成都 / 贵阳 / 昆明 / 南宁 / 拉萨 / 海口 / 三亚 (海南省会海口,
 *   三亚为计划单列) / 杭州 / 福州 / 南昌 / 广州
 * - 5 计划单列市: 大连 / 青岛 / 宁波 / 厦门 / 深圳
 * 合计 4 + 27 + 5 = 36 (港澳不计入 — 高德 adcode 体系不同, M2 再补)
 *
 * adcode 一一对应中华人民共和国行政区划代码 (GB/T 2260); 2026-09 数据
 * 来自 [高德 /config/district] 公开响应快照.
 */

export interface CnCityEntry {
  /** 中文显示名 — 与高德 district.name 完全一致 */
  name: string
  /** 6 位数字 adcode — Province/直辖市 级别 */
  adcode: string
}

export const CN_CITIES: readonly CnCityEntry[] = [
  // ---- 4 直辖市 ----
  { name: '北京市', adcode: '110000' },
  { name: '天津市', adcode: '120000' },
  { name: '上海市', adcode: '310000' },
  { name: '重庆市', adcode: '500000' },
  // ---- 27 省会 / 自治区首府 (按拼音首字母排序) ----
  { name: '哈尔滨市', adcode: '230100' },
  { name: '长春市', adcode: '220100' },
  { name: '沈阳市', adcode: '210100' },
  { name: '呼和浩特市', adcode: '150100' },
  { name: '乌鲁木齐市', adcode: '650100' },
  { name: '兰州市', adcode: '620100' },
  { name: '西宁市', adcode: '630100' },
  { name: '西安市', adcode: '610100' },
  { name: '银川市', adcode: '640100' },
  { name: '郑州市', adcode: '410100' },
  { name: '济南市', adcode: '370100' },
  { name: '石家庄市', adcode: '130100' },
  { name: '太原市', adcode: '140100' },
  { name: '合肥市', adcode: '340100' },
  { name: '武汉市', adcode: '420100' },
  { name: '长沙市', adcode: '430100' },
  { name: '南京市', adcode: '320100' },
  { name: '成都市', adcode: '510100' },
  { name: '贵阳市', adcode: '520100' },
  { name: '昆明市', adcode: '530100' },
  { name: '南宁市', adcode: '450100' },
  { name: '拉萨市', adcode: '540100' },
  { name: '海口市', adcode: '460100' },
  { name: '杭州市', adcode: '330100' },
  { name: '福州市', adcode: '350100' },
  { name: '南昌市', adcode: '360100' },
  { name: '广州市', adcode: '440100' },
  // ---- 5 计划单列市 ----
  { name: '大连市', adcode: '210200' },
  { name: '青岛市', adcode: '370200' },
  { name: '宁波市', adcode: '330200' },
  { name: '厦门市', adcode: '350200' },
  { name: '深圳市', adcode: '440300' },
] as const

/** 按 name 查询 — AddressPickerDialog 省级 select 用. */
export function findCityByName(name: string): CnCityEntry | undefined {
  return CN_CITIES.find((c) => c.name === name)
}

/** 按 adcode 查询 — regeo 回调时根据 adcode 自动选回省级. */
export function findCityByAdcode(adcode: string): CnCityEntry | undefined {
  return CN_CITIES.find((c) => c.adcode === adcode)
}
