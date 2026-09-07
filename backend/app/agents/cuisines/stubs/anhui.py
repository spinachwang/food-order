"""徽菜专家 stub — see F003 §3.1 and F017 spec."""
from app.agents.cuisines.base import BaseCuisineExpert

CUISINE_PROMPT_FRAGMENT = """
- 代表菜：臭鳜鱼、毛豆腐、火腿炖甲鱼、徽州毛豆腐、问政山笋
- 腊味：徽州腊肉、刀板香
- 风味：重油 / 重色 / 咸鲜 / 腊香 / 山珍（徽州山区特色）
- 与川菜区别：徽偏"咸鲜 + 重油"不辣，川偏"麻辣"；用户只说"重口味"
  两者都可，但说"咸鲜 / 不辣 / 山珍 / 火腿"则优先徽
- 与湘菜区别：徽偏"山珍腊味 + 咸鲜"，湘偏"香辣腊味"；同样腊味场景
  优先徽
- 过敏原注意：徽菜常用火腿、腊肉（徽州腊肉 / 刀板香）、部分菜用料酒；
  忌 pork / alcohol 者点单时确认
- 关键词生成：包含"徽菜 / 安徽 / 徽州"中的 1-2 个 + 1 个代表菜
  （"臭鳜鱼" / "毛豆腐" / "火腿炖甲鱼"）+ 1 个风味词（"咸鲜" / "重油"）
"""


class AnhuiExpert(BaseCuisineExpert):
    cuisine_id = "anhui"
    display_name = "徽菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
