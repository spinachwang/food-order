"""小吃专家 stub — see F003 §3.1 and F023 spec.

F023 §4 prompt 要点:
- 范围:街头 / 摊位 / 非正餐类小吃摊 / 街边店; 人均 10-30 元
- 与中式快餐(F022)边界:本 Node 推非正餐类小吃摊 / 街边店; 简餐类
  (饭类套餐 / 面食快餐 等)归 F022
- 关键词生成:包含"小吃 / 街头"中的 1 个 + 1 个代表菜("煎饼"、"麻辣烫")
"""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表品类:
  - 北方:煎饼、烤冷面、肉夹馍、凉皮
  - 川渝:麻辣烫、钵钵鸡、串串、烤脑花
  - 关东:关东煮
  - 烧烤:烤串、烤翅、烤面筋
- 风味:街头 / 浓郁 / 重口 / 区域性强 / 出餐快
- 范围:街头 / 摊位 / 非正餐类小吃摊 / 街边店, 人均 10-30 元
- 与中式快餐(F022)边界:本 Node 推非正餐类小吃摊 / 街边店 (摊位 / 档口,
  无座位或简易座位); 中式快餐归 F022 (有座位 / 标准菜单 / 饭类套餐的简餐,
  例如饭类套餐、面食快餐等)
- 过敏原注意:油炸 / 辣 / 含麸质普遍; 多数可选配料需询问
- 关键词生成:包含"小吃 / 街头"中的 1 个 + 1 个代表菜
  ("煎饼"、"麻辣烫"、"烤串"、"关东煮")
"""


class SnacksExpert(BaseCuisineExpert):
    cuisine_id = "snacks"
    display_name = "小吃"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
