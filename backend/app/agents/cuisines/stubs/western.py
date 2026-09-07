"""西餐专家 stub — see F003 §3.1 and F019 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：牛排（菲力 / 西冷 / 肋眼 / 战斧）、意面、烩饭、披萨（意式 / 薄底）、
  沙拉（凯撒沙拉 / 尼斯沙拉）、烤鸡 / 烤鱼
- 风味：奶香 / 番茄 / 香草 / 黑胡椒 / 烧烤 / 黄油 / 红酒
- 范围：意式、法式、美式西餐聚合——以正餐为主，人均 ≥ 80 元
- 与西式快餐（F020）边界：本 Node 推人均 ≥ 80 元的正餐西餐厅；
  人均 < 80、快餐式披萨（如必胜客欢乐餐厅）、连锁快餐档归 F020
- 过敏原注意：奶制品（dairy）/ 麸质（gluten，面食、面包）/ 坚果（nuts，部分酱汁
  如 pesto 含松子）常见；忌 dairy / gluten / nuts 者点单时确认
- 关键词生成：包含"西餐 / 意餐 / 法餐"中的 1 个 + 1 个代表菜
  （"牛排" / "意面" / "披萨" / "烩饭" / "沙拉"）+ 1 个风味词
  （"奶香" / "番茄" / "香草" / "黑胡椒"）
- 餐厅筛选：人均 ≥ 80 元、评分 ≥ 4.0
"""


class WesternExpert(BaseCuisineExpert):
    cuisine_id = "western"
    display_name = "西餐"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
