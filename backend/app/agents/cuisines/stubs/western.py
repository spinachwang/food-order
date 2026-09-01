"""西餐专家 stub — see F003 §3.1 and F019 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：牛排、意面、披萨、沙拉、烩饭
- 风味：奶香 / 烧烤 / 番茄 / 香草 / 黑胡椒
- 范围：意式、法式、美式西餐聚合；与西式快餐区别是用餐时长与菜品档次
- 过敏原注意：奶制品 / 麸质 / 坚果（部分酱汁）常见
- 关键词生成：菜系词（西餐/西餐厅/意餐/法餐）+ 类别（牛排/意面/沙拉）+ 风味
"""


class WesternExpert(BaseCuisineExpert):
    cuisine_id = "western"
    display_name = "西餐"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
