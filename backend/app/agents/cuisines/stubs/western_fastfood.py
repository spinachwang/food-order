"""西式快餐专家 stub — see F003 §3.1 and F020 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表品类：汉堡、薯条、炸鸡、披萨（连锁快餐档）、可乐、便利店便当
- 代表品牌：
  - 汉堡：麦当劳、肯德基、汉堡王
  - 披萨：必胜客、达美乐
  - 便利店便当：7-11、全家、罗森
- 风味：快餐口感 / 出餐快 / 高盐 / 高热量 / 标准化口味 / 单人份
- 与西餐（F019）边界：本 Node 推人均 < 80 元的西式快餐；正餐西餐厅归
  F019，必胜客欢乐餐厅等人均较低的快餐式披萨也归本菜系
- 与日料（F018）边界：便利店日式便当归本菜系——非正餐日料；
  正餐日料店归 F018
- 过敏原注意：油炸物（fried_food）默认含；含麸质（gluten，面包胚、披萨
  饼底）/ dairy（奶酪、芝士）普遍；忌油炸 / 麸质 / 奶制品者点单时确认
- 关键词生成：包含"汉堡 / 炸鸡 / 披萨 / 便利店便当"中的 2 个
  + 1 个风味词（"快餐" / "快" / "出餐快" / "标准化"）
- 餐厅筛选：人均 < 80 元、出餐快、含连锁快餐档或便利店
"""


class WesternFastfoodExpert(BaseCuisineExpert):
    cuisine_id = "western_fastfood"
    display_name = "西式快餐"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
