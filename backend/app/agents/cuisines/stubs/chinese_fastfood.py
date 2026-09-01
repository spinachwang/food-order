"""中式快餐专家 stub — see F003 §3.1 and F022 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表品类：盖浇饭、炒饭、炒面、黄焖鸡、沙县小吃（连锁档）
- 风味：家常 / 浓郁 / 饭类主食 / 出餐快
- 与传统八大菜系区别：快餐出餐快、份饭套餐、单人份
- 过敏原注意：部分使用味精、酱油；少数含花生碎
- 关键词生成：菜系词（中式快餐/盖浇饭/炒饭/快餐）+ 主食类别 + 配菜
"""


class ChineseFastfoodExpert(BaseCuisineExpert):
    cuisine_id = "chinese_fastfood"
    display_name = "中式快餐"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
