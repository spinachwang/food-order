"""川菜专家 stub — see F003 §3.1 and F010 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：麻婆豆腐、水煮鱼、回锅肉、鱼香肉丝、夫妻肺片
- 风味：麻辣 / 鲜香 / 糊辣 / 鱼香
- 与湘菜区别：川偏"麻"，湘偏"辣"
- 过敏原注意：川菜常用花生油、豆瓣酱；忌花生者要点单时确认
- 关键词生成：必须包含 1 个菜系词（川/四川/川菜）+ 1 个代表菜 + 1 个风味词
"""


class SichuanExpert(BaseCuisineExpert):
    cuisine_id = "sichuan"
    display_name = "川菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
