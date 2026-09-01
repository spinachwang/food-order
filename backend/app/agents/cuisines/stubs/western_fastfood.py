"""西式快餐专家 stub — see F003 §3.1 and F020 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表品类：汉堡、薯条、炸鸡、披萨（连锁快餐档）、可乐
- 风味：油炸 / 高盐 / 快餐口感 / 高热量
- 与西餐区别：快餐出餐快、用餐时间短、单人份
- 过敏原注意：油炸物（fried_food）默认含；含麸质 / dairy 普遍
- 关键词生成：菜系词（西式快餐/汉堡/披萨）+ 品牌词（麦当劳/肯德基/必胜客）+ 品类
"""


class WesternFastfoodExpert(BaseCuisineExpert):
    cuisine_id = "western_fastfood"
    display_name = "西式快餐"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
