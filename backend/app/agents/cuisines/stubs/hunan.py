"""湘菜专家 stub — see F003 §3.1 and F016 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：剁椒鱼头、毛氏红烧肉、湘西外婆菜、农家小炒肉、腊肉、腊鱼、腊鸡
- 小吃：臭豆腐、糖油粑粑
- 风味：香辣 / 腊味 / 酸辣 / 浓郁 / 乡土气息浓
- 与川菜区别：湘偏"香辣 + 腊味 + 剁椒"，川偏"麻辣 + 花椒"；
  用户只说"辣"时两者都可，但说"香辣 / 腊味 / 剁椒"则优先湘
- 过敏原注意：腊味常用烟熏（腊肉 / 腊鱼）、部分菜含花生 / 辣椒油；
  忌 peanut / soy / 烟熏者需点单时确认
- 关键词生成：包含"湘菜 / 湖南"中的 1 个 + 1 个代表菜
  （"剁椒鱼头" / "腊味"）+ 1 个风味词（"香辣"）
"""


class HunanExpert(BaseCuisineExpert):
    cuisine_id = "hunan"
    display_name = "湘菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
