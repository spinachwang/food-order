"""粤菜专家 stub — see F003 §3.1 and F011 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：白切鸡、烧鹅、清蒸石斑、蜜汁叉烧、广式早茶
- 风味：清淡 / 原味 / 鲜甜 / 煲汤
- 范围广：含早茶、烧腊、海鲜、糖水；推荐时按时间段拆分
- 过敏原注意：粤菜常用蚝油、海鲜高汤；忌 shellfish / fish 者需确认
- 关键词生成：菜系词（粤/广东/粤菜）+ 时间段（早茶 / 午餐 / 晚餐）+ 代表菜
"""


class CantoneseExpert(BaseCuisineExpert):
    cuisine_id = "cantonese"
    display_name = "粤菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
