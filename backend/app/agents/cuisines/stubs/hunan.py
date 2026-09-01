"""湘菜专家 stub — see F003 §3.1 and F016 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：剁椒鱼头、毛氏红烧肉、辣椒炒肉、腊味合蒸
- 风味：香辣 / 腊味 / 酸辣 / 浓郁
- 与川菜区别：湘偏"辣"，川偏"麻"
- 过敏原注意：腊味常用烟熏；少数含花生
- 关键词生成：菜系词（湘/湖南/湘菜）+ 代表菜 + 风味
"""


class HunanExpert(BaseCuisineExpert):
    cuisine_id = "hunan"
    display_name = "湘菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
