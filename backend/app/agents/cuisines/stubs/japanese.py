"""日料专家 stub — see F003 §3.1 and F018 spec."""

from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：寿司、刺身、拉面、乌冬、荞麦面、天妇罗、可乐饼、鳗鱼饭、亲子丼、牛丼
- 三大代表：寿司 / 刺身 / 拉面（日料辨识度的核心三件）
- 风味：生鲜 / 刀工 / 季节感 / 和风 / 鲜味 / 原味 / 摆盘讲究
- 与西式快餐（F020）边界：本 Node 推荐正餐日料店（寿司店 / 拉面店 / 居酒屋
  / 鳗鱼饭专门店）；便利店日式便当归 F020 西式快餐——用户说"便利店便当"
  时不要推本 Node
- 过敏原注意：刺身 / 海鲜类含贝类、鱼（shellfish / fish）过敏原；部分拉面含
  小麦 + 蛋 + 麸质；忌海鲜 / 蛋 / 麸质者需确认
- 关键词生成：包含"日料 / 日本料理"中的 1 个 + 1 个代表菜（"寿司" /
  "刺身" / "拉面" / "鳗鱼饭" / "天妇罗"）+ 1 个风味词（"和风" / "生鲜"）
"""


class JapaneseExpert(BaseCuisineExpert):
    cuisine_id = "japanese"
    display_name = "日料"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
