"""小吃专家 stub — see F003 §3.1 and F023 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表品类：煎饼、肉夹馍、凉皮、烤冷面、麻辣烫、烧烤、炸串
- 风味：街头 / 浓郁 / 重口 / 区域性强
- 范围：早餐小吃、夜宵小吃、街头小吃三类场景
- 过敏原注意：油炸 / 辣 / 含麸质普遍；多数可选配料需询问
- 关键词生成：菜系词（小吃/街头小吃/夜宵/早餐）+ 品类 + 区域（如"国贸"/"三里屯"）
"""


class SnacksExpert(BaseCuisineExpert):
    cuisine_id = "snacks"
    display_name = "小吃"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
