"""徽菜专家 stub — see F003 §3.1 and F017 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：臭鳜鱼、毛豆腐、徽州毛豆腐、火腿炖甲鱼
- 风味：咸鲜 / 重油重色 / 腊香 / 山野
- 与浙菜区别：徽偏"重油重色"，浙偏"清鲜"
- 过敏原注意：徽菜常用火腿、腊肉；忌 pork 不常见但需注意
- 关键词生成：菜系词（徽/安徽/徽菜）+ 代表菜 + 风味
"""


class AnhuiExpert(BaseCuisineExpert):
    cuisine_id = "anhui"
    display_name = "徽菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
