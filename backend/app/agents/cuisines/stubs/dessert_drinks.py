"""甜品饮品专家 stub — see F003 §3.1 and F024 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表品类：奶茶、咖啡、蛋糕、冰淇淋、糖水、酸奶
- 风味：甜 / 冷热两宜 / 颜值高 / 下午茶
- 范围：含连锁饮品（喜茶/星巴克/瑞幸）+ 烘焙甜品 + 中式糖水
- 过敏原注意：dairy / 花生（部分甜品含坚果）/ 酒精（部分甜点含）
- 关键词生成：菜系词（甜品/饮品/奶茶/咖啡/糖水）+ 类别 + 风味
"""


class DessertDrinksExpert(BaseCuisineExpert):
    cuisine_id = "dessert_drinks"
    display_name = "甜品饮品"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
