"""闽菜专家 stub — see F003 §3.1 and F015 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：佛跳墙、海蛎煎、沙茶面、荔枝肉、闽南春卷、鸡汤汆海蚌
- 风味：汤鲜 / 山珍 / 清淡 / 刀工巧妙 / 海味醇厚
- 范围：含福州菜、闽南菜、闽西菜三路风味；沙茶面偏闽南、佛跳墙偏福州
- 与粤菜区别：闽更"汤鲜 + 山珍"，粤更"生猛海鲜"；用户说"海味汤品 / 山珍"
  优先闽，说"生猛海鲜 / 早茶"优先粤
- 过敏原注意：闽菜大量海鲜（海蛎、虾、贝）、鸡汤海蚌含贝类；忌 shellfish /
  fish / 鸡汤者几乎无菜可吃，需显式提示并返回 matched_allergies
- 关键词生成：菜系词（闽菜 / 福建 / 闽南 / 沙茶）中 1-2 个 + 1 个代表菜
  + 1 个风味词（"汤鲜" / "海味"）；用户提及"沙茶"时优先用"沙茶面"作代表菜
"""



class FujianExpert(BaseCuisineExpert):
    cuisine_id = "fujian"
    display_name = "闽菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
