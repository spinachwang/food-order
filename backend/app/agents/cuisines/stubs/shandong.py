"""鲁菜专家 stub — see F003 §3.1 and F012 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：糖醋鲤鱼、九转大肠、葱烧海参、油爆双脆
- 风味：咸鲜 / 葱香 / 酱香 / 爆炒
- 与淮扬菜（苏菜）区别：鲁偏"咸鲜厚重"，苏偏"清淡精致"
- 过敏原注意：鲁菜葱用量大；少数菜用花椒
- 关键词生成：菜系词（鲁/山东/鲁菜）+ 代表菜 + 风味词
"""


class ShandongExpert(BaseCuisineExpert):
    cuisine_id = "shandong"
    display_name = "鲁菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
