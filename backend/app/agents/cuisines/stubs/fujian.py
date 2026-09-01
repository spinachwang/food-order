"""闽菜专家 stub — see F003 §3.1 and F015 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：佛跳墙、海蛎煎、沙茶面、荔枝肉
- 风味：鲜醇 / 清淡 / 汤水讲究 / 海味
- 范围：以福州、闽南、闽西三路风味聚合
- 过敏原注意：闽菜大量海鲜（海蛎、虾、贝）；忌 shellfish / fish 者几乎无菜可吃
- 关键词生成：菜系词（闽/福建/闽菜）+ 代表菜 + 风味
"""


class FujianExpert(BaseCuisineExpert):
    cuisine_id = "fujian"
    display_name = "闽菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
