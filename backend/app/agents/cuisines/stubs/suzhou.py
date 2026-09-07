"""苏菜专家 stub — see F003 §3.1 and F013 spec."""

from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：松鼠鳜鱼、蟹粉狮子头、响油鳝糊、盐水鸭
- 淮扬代表：蟹黄汤包、文楼干贝、扬州炒饭
- 风味：精致 / 微甜 / 刀工细腻 / 原汁原味
- 范围：含淮扬菜（扬州 / 淮安 / 镇江），南京 / 苏州 / 无锡风味略有差异
- 与浙菜区别：苏菜偏甜鲜精致，浙菜偏清淡江浙；用户说"清淡偏甜"优先苏
- 与粤菜区别：粤菜更广式 + 海鲜为主，苏菜以江淮河鲜 + 刀工见长
- 过敏原注意：蟹粉 / 鱼圆 / 河鲜常见；忌 shellfish / fish 者需避
- 关键词生成：菜系词（苏菜 / 江苏 / 苏帮 / 淮扬）中 1-2 个 + 1 个代表菜
  + 1 个风味词（"精致" / "微甜" / "刀工"）；不得只含"清淡"作为风味词
  —— 那是浙菜的标签
"""


class SuzhouExpert(BaseCuisineExpert):
    cuisine_id = "suzhou"
    display_name = "苏菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
