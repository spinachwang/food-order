"""日料专家 stub — see F003 §3.1 and F018 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：寿司、刺身、拉面、天妇罗、鳗鱼饭
- 风味：鲜味 / 原味 / 季节感 / 摆盘讲究
- 范围：含寿司、刺身、烤物、煮物、炸物、面食
- 过敏原注意：刺身含鱼 / shellfish；天妇罗油炸；拉面常用含麸质面粉
- 关键词生成：菜系词（日料/日本料理）+ 类别（寿司/拉面/天妇罗/定食）+ 风味
"""


class JapaneseExpert(BaseCuisineExpert):
    cuisine_id = "japanese"
    display_name = "日料"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
