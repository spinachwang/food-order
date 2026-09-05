"""浙菜专家 stub — see F003 §3.1 and F014 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：西湖醋鱼、东坡肉、龙井虾仁、宋嫂鱼羹
- 杭帮：西湖醋鱼、东坡肉、龙井虾仁、宋嫂鱼羹
- 宁波：宁波汤圆、雪菜黄鱼
- 温州：鱼丸、三丝敲鱼
- 风味：清鲜 / 嫩滑 / 醇正 / 原汁原味 / 细巧
- 与苏菜区别：浙更"鲜"，苏更"甜"；用户说"清淡"优先浙，说"偏甜"优先苏
- 与粤菜区别：浙更江浙本土河鲜 + 刀工细巧，粤更广式海鲜 + 煲汤；
  用户说"海鲜"时优先粤，说"江浙本地"时优先浙
- 过敏原注意：浙菜多用黄酒（烹腥）；常见含虾仁（龙井虾仁）、蟹（梭子蟹）；
  忌 shellfish / fish / alcohol 者需避
- 关键词生成：菜系词（浙菜 / 浙江 / 杭帮 / 宁波 / 温州）中 1-2 个 +
  1 个代表菜 + 1 个风味词（"清鲜"）；用户提及具体派别（杭帮/宁波/温州）
  时优先用该派别词 + 派别代表菜
"""


class ZhejiangExpert(BaseCuisineExpert):
    cuisine_id = "zhejiang"
    display_name = "浙菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
