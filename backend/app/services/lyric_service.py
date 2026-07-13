"""
AI 作词服务
基于 LLM 的歌词生成服务，支持多种风格、主题和语言

功能:
- 主题作词 (根据主题生成完整歌词)
- 续写歌词 (根据已有歌词续写)
- 押韵优化 (改进韵律)
- 多语言支持 (中文/英文/日文等)
"""

from typing import Optional, List
from pydantic import BaseModel
import httpx
import os

# Gemini API Key (与现有 Gemini 配置共享)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_key")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


class LyricStyle(BaseModel):
    """歌词风格配置"""
    name: str
    description: str
    keywords: List[str]


class LyricRequest(BaseModel):
    """歌词生成请求"""
    theme: str  # 主题 (如 "爱情", "梦想", "旅行")
    style: Optional[str] = "pop"  # 风格
    language: Optional[str] = "zh"  # 语言 (zh/en/ja)
    mood: Optional[str] = "happy"  # 情绪 (happy/sad/energetic/romantic)
    structure: Optional[str] = "verse-chorus-verse-chorus-bridge-chorus"  # 结构
    custom_lyrics: Optional[str] = None  # 已有歌词 (用于续写)
    rhyme_scheme: Optional[str] = "AABB"  # 押韵方案 (AABB/ABAB/自由)


class LyricResponse(BaseModel):
    """歌词生成响应"""
    success: bool
    lyrics: str
    structure: str
    syllable_count: Optional[int] = None
    rhyme_analysis: Optional[str] = None
    message: str


# 预设歌词风格库
LYRIC_STYLES = [
    LyricStyle(
        name="pop",
        description="流行情歌",
        keywords=["爱情", "情感", "旋律", "副歌", "押韵"]
    ),
    LyricStyle(
        name="rap",
        description="说唱/嘻哈",
        keywords=["节奏", "flow", "韵脚", "freestyle", "态度"]
    ),
    LyricStyle(
        name="rock",
        description="摇滚",
        keywords=["力量", "激情", "反叛", "吉他", "呐喊"]
    ),
    LyricStyle(
        name="folk",
        description="民谣",
        keywords=["叙事", "诗意", "生活", "吉他", "温暖"]
    ),
    LyricStyle(
        name="electronic",
        description="电子音乐",
        keywords=["节奏", "重复", "氛围", "drop", "合成器"]
    ),
    LyricStyle(
        name="rnb",
        description="R&B 节奏蓝调",
        keywords=["节奏", "情感", "转音", "soul", "groove"]
    ),
    LyricStyle(
        name="country",
        description="乡村音乐",
        keywords=["故事", "吉他", "家乡", "生活", "简单"]
    ),
    LyricStyle(
        name="jazz",
        description="爵士",
        keywords=["即兴", "慵懒", "萨克斯", "swing", "夜晚"]
    ),
]

# 情绪关键词
MOOD_KEYWORDS = {
    "happy": ["快乐", "阳光", "积极", "活力", "微笑", "希望"],
    "sad": ["悲伤", "眼泪", "孤独", "回忆", "失落", "思念"],
    "energetic": ["能量", "激情", "动力", "战斗", "突破", "燃烧"],
    "romantic": ["爱情", "温柔", "亲吻", "拥抱", "心跳", "永恒"],
    "angry": ["愤怒", "反抗", "呐喊", "力量", "突破", "革命"],
    "nostalgic": ["怀旧", "回忆", "过去", "童年", "老家", "时光"],
}


class LyricService:
    """AI 作词服务"""
    
    def __init__(self):
        self.styles = {s.name: s for s in LYRIC_STYLES}
        self.moods = MOOD_KEYWORDS
    
    def get_available_styles(self) -> List[dict]:
        """获取可用风格列表"""
        return [
            {"name": s.name, "description": s.description}
            for s in LYRIC_STYLES
        ]
    
    def get_available_moods(self) -> List[str]:
        """获取可用情绪列表"""
        return list(MOOD_KEYWORDS.keys())
    
    async def generate_lyrics(self, request: LyricRequest) -> LyricResponse:
        """生成歌词"""
        try:
            # 构建提示词
            prompt = self._build_prompt(request)
            
            # 调用 Gemini API
            lyrics = await self._call_gemini(prompt)
            
            # 解析歌词结构
            structure = self._parse_structure(lyrics)
            
            # 押韵分析
            rhyme_analysis = self._analyze_rhyme(lyrics, request.language)
            
            return LyricResponse(
                success=True,
                lyrics=lyrics,
                structure=structure,
                message="✅ 歌词生成成功",
                rhyme_analysis=rhyme_analysis
            )
        
        except Exception as e:
            return LyricResponse(
                success=False,
                lyrics="",
                structure="",
                message=f"❌ 歌词生成失败：{str(e)}"
            )
    
    async def continue_lyrics(self, existing_lyrics: str, style: str = "pop") -> LyricResponse:
        """续写歌词"""
        request = LyricRequest(
            theme="根据已有歌词续写",
            style=style,
            custom_lyrics=existing_lyrics
        )
        return await self.generate_lyrics(request)
    
    def _build_prompt(self, request: LyricRequest) -> str:
        """构建 Gemini 提示词"""
        style_info = self.styles.get(request.style, self.styles["pop"])
        mood_keywords = self.moods.get(request.mood, [])
        
        # 基础提示词
        prompt = f"""你是一位专业的歌词创作人，请根据以下要求创作一首歌曲的歌词：

**主题**: {request.theme}
**风格**: {style_info.description} ({', '.join(style_info.keywords)})
**情绪**: {request.mood} ({', '.join(mood_keywords)})
**语言**: {self._get_language_name(request.language)}
**结构**: {request.structure}
**押韵方案**: {request.rhyme_scheme}

**要求**:
1. 歌词要有画面感和情感共鸣
2. 符合{style_info.name}风格的特点
3. 注意押韵和节奏感
4. 副歌部分要朗朗上口、容易记忆
5. 使用{self._get_language_name(request.language)}创作

请按照以下格式输出:
[Verse 1]
(第一段歌词)

[Chorus]
(副歌歌词)

[Verse 2]
(第二段歌词)

[Chorus]
(副歌重复)

[Bridge]
(桥段歌词)

[Chorus]
(副歌重复，可以有变化)
"""
        
        # 如果有已有歌词，用于续写
        if request.custom_lyrics:
            prompt += f"\n\n**已有歌词** (请在此基础上续写):\n{request.custom_lyrics}"
        
        return prompt
    
    def _get_language_name(self, lang_code: str) -> str:
        """获取语言名称"""
        lang_map = {
            "zh": "中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韩文",
            "es": "西班牙文",
            "fr": "法文",
        }
        return lang_map.get(lang_code, "中文")
    
    async def _call_gemini(self, prompt: str) -> str:
        """调用 Gemini API 生成歌词"""
        if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_key":
            # Mock 模式
            return self._mock_lyrics(prompt)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    GEMINI_API_URL,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{
                            "parts": [{"text": prompt}]
                        }],
                        "generationConfig": {
                            "temperature": 0.7,
                            "topK": 40,
                            "topP": 0.95,
                            "maxOutputTokens": 2048,
                        }
                    },
                    params={"key": GEMINI_API_KEY}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    raise Exception(f"Gemini API error: {response.status_code}")
        
        except Exception as e:
            # 降级到 Mock
            print(f"Gemini API 失败，降级到 Mock: {e}")
            return self._mock_lyrics(prompt)
    
    def _mock_lyrics(self, prompt: str) -> str:
        """Mock 歌词生成 (当 API 不可用时)"""
        return """[Verse 1]
阳光洒在窗台 微风轻轻吹来
心中的梦想 从未曾离开
一步一脚印 走向未来
相信总有一天 会绽放光彩

[Chorus]
追逐梦想的路上 有你有我相伴
风雨再多也不怕 勇敢向前闯
心中的火焰 永远不会熄灭
让我们一起飞翔 在梦想的天空

[Verse 2]
回忆里的笑容 温暖我的心房
每一次跌倒 都是成长的力量
握紧双手 不放弃希望
明天会更好 我们相信

[Chorus]
追逐梦想的路上 有你有我相伴
风雨再多也不怕 勇敢向前闯
心中的火焰 永远不会熄灭
让我们一起飞翔 在梦想的天空

[Bridge]
就算世界变得复杂
我们依然保持初心
手牵手一起走下去
这就是最美好的旅程

[Chorus]
追逐梦想的路上 有你有我相伴
风雨再多也不怕 勇敢向前闯
心中的火焰 永远不会熄灭
让我们一起飞翔 在梦想的天空"""
    
    def _parse_structure(self, lyrics: str) -> str:
        """解析歌词结构"""
        sections = []
        if "[Verse]" in lyrics or "[Verse 1]" in lyrics:
            sections.append("Verse")
        if "[Chorus]" in lyrics:
            sections.append("Chorus")
        if "[Bridge]" in lyrics:
            sections.append("Bridge")
        if "[Pre-Chorus]" in lyrics:
            sections.append("Pre-Chorus")
        if "[Outro]" in lyrics:
            sections.append("Outro")
        
        return "-".join(sections) if sections else "Unknown"
    
    def _analyze_rhyme(self, lyrics: str, language: str = "zh") -> str:
        """简单押韵分析"""
        # 提取每行末尾字/词
        lines = [l.strip() for l in lyrics.split('\n') if l.strip() and not l.strip().startswith('[')]
        
        if not lines:
            return "无法分析"
        
        # 取每行最后一个字 (中文) 或单词 (英文)
        endings = []
        for line in lines:
            if language == "zh":
                endings.append(line[-1] if line else "")
            else:
                words = line.split()
                endings.append(words[-1] if words else "")
        
        # 简单分组
        rhyme_groups = {}
        for i, ending in enumerate(endings):
            if ending not in rhyme_groups:
                rhyme_groups[ending] = []
            rhyme_groups[ending].append(i + 1)
        
        # 生成分析报告
        analysis = []
        for ending, positions in rhyme_groups.items():
            if len(positions) >= 2:
                analysis.append(f"韵脚 \"{ending}\": 第 {', '.join(map(str, positions))} 行")
        
        return "\n".join(analysis) if analysis else "未检测到明显押韵模式"


# 全局服务实例
lyric_service = LyricService()