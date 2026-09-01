"""苏菜专家 stub — see F003 §3.1 and F013 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：松鼠鳜鱼、蟹粉狮子头、鸡汤煮干丝、清炖蟹粉狮子头
- 风味：清淡 / 精致 / 微甜 / 刀工细腻
- 范围：含淮扬菜（扬州、淮安）；南京、苏州、无锡风味略不同
- 过敏原注意：蟹粉 / 鱼圆常见；忌 shellfish / fish 者需避
- 关键词生成：菜系词（苏/江苏/淮扬/苏菜）+ 代表菜 + 风味
"""


class SuzhouExpert(BaseCuisineExpert):
    cuisine_id = "suzhou"
    display_name = "苏菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
