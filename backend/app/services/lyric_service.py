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

from fastapi import HTTPException
from pydantic import BaseModel

from app.services.lyrics_engine import lyrics_engine



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
        """生成歌词（P4-B2 Phase B-3：双 Provider 引擎——Yinchao primary → TemPolor Lyric v1 backup）"""
        # 构建提示词
        prompt = self._build_prompt(request)

        # Phase B-3 裁定 2：最终组合 prompt 超过 Yinchao 官方上限（2000 字符）
        # → 显式失败（HTTP 400 语义），不调用任何 Provider、不静默截断、
        #   不产生 Credits 变化。
        if len(prompt) > 2000:
            raise HTTPException(
                status_code=400,
                detail="歌词主题或内容过长（上限 2000 字符），请精简后重试",
            )

        # 双 Provider 编排（45s 全局 hard deadline 由 lyrics_engine 约束）
        result = await lyrics_engine.generate(prompt)

        if result.status != "succeeded":
            return LyricResponse(
                success=False,
                lyrics="",
                structure=request.structure,
                message=f"❌ 歌词生成失败：{result.error or '未知原因'}",
            )

        # 解析歌词结构
        structure = self._parse_structure(result.lyric)

        # 押韵分析
        rhyme_analysis = self._analyze_rhyme(result.lyric, request.language)

        return LyricResponse(
            success=True,
            lyrics=result.lyric,
            structure=structure,
            message="✅ 歌词生成成功",
            rhyme_analysis=rhyme_analysis,
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