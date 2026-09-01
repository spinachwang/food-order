"""浙菜专家 stub — see F003 §3.1 and F014 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：西湖醋鱼、东坡肉、龙井虾仁、宋嫂鱼羹
- 风味：清鲜 / 嫩滑 / 醇正 / 原汁原味
- 与苏菜区别：浙更"鲜"，苏更"甜"
- 过敏原注意：浙菜多用黄酒；少数含虾仁 / 蟹
- 关键词生成：菜系词（浙/浙江/杭帮/浙菜）+ 代表菜 + 风味
"""


class ZhejiangExpert(BaseCuisineExpert):
    cuisine_id = "zhejiang"
    display_name = "浙菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
