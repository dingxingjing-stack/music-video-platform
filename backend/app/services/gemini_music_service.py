"""
Gemini AI 音乐生成服务（开发阶段临时方案）
- 使用 Gemini 优化音乐提示词
- 返回 Mock 音频 URL（开发阶段）
- 正式上线时替换为 Mureka API
"""

import httpx
import os
from typing import Optional, Dict, Any
from pydantic import BaseModel


class GeminiSongRequest(BaseModel):
    """Gemini 音乐生成请求"""
    prompt: str  # 原始提示词
    style: str  # 音乐风格
    duration: int = 180  # 时长（秒）
    type: str = "song"  # song/music/bgm
    # Phase 1 新增参数
    vocal_type: str = "auto"  # auto/male/female/instrumental 人声类型
    weirdness: float = 0.5  # 0-1 风格偏离度
    style_strength: float = 0.7  # 0-1 风格强度
    structure: Optional[str] = None  # 歌曲结构 JSON: intro/verse/chorus/bridge/outro
    lyrics: Optional[str] = None  # 自定义歌词


class GeminiSongResponse(BaseModel):
    """Gemini 音乐生成响应"""
    success: bool
    audio_url: Optional[str]
    optimized_prompt: Optional[str]  # Gemini 优化的提示词
    style_suggestions: Optional[list]
    error: Optional[str]
    task_id: Optional[str]
    generated_lyrics: Optional[str] = None  # 生成的歌词（如未提供）


class GeminiService:
    """Gemini AI 音乐生成服务（开发阶段）"""
    
    # Gemini API 配置
    API_KEY = os.getenv("GEMINI_API_KEY", "")  # 从环境变量读取
    API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    # Mock 音频示例（开发阶段使用）
    MOCK_AUDIO_URLS = [
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
    ]
    
    # 风格映射（中文→英文）
    STYLE_MAP = {
        "pop": "Pop music",
        "摇滚": "Rock music",
        "电子": "Electronic/Dance music",
        "嘻哈": "Hip-hop/Rap music",
        "r&b": "R&B/Soul music",
        "爵士": "Jazz music",
        "古典": "Classical music",
        "氛围": "Ambient music",
        "电影配乐": "Cinematic/Soundtrack music",
        "lo-fi": "Lo-fi/Chill music",
    }
    
    async def generate_song(self, request: GeminiSongRequest) -> GeminiSongResponse:
        """生成音乐（开发阶段：Gemini 优化提示词 + Mock 音频）"""
        try:
            # 1. 使用 Gemini 优化提示词（如果配置了 API Key）
            optimized_prompt = request.prompt
            style_suggestions = []
            generated_lyrics = None
            
            if self.API_KEY:
                optimized_prompt, style_suggestions, generated_lyrics = await self._optimize_prompt_with_gemini(request)
            
            # 2. 如果用户没提供歌词且 Gemini 生成了，使用 Gemini 的
            if not request.lyrics and generated_lyrics:
                pass  # 已赋值
            elif request.lyrics:
                generated_lyrics = request.lyrics
            
            # 3. 返回 Mock 音频 URL（开发阶段）
            import random
            audio_url = random.choice(self.MOCK_AUDIO_URLS)
            
            return GeminiSongResponse(
                success=True,
                audio_url=audio_url,
                optimized_prompt=optimized_prompt,
                style_suggestions=style_suggestions,
                error=None,
                task_id=f"gemini-{os.urandom(4).hex()}",
                generated_lyrics=generated_lyrics
            )
            
        except Exception as e:
            return GeminiSongResponse(
                success=False,
                audio_url=None,
                optimized_prompt=None,
                style_suggestions=[],
                error=f"Gemini 服务错误：{str(e)}",
                task_id=None
            )
    
    async def _optimize_prompt_with_gemini(self, request: GeminiSongRequest) -> tuple:
        """使用 Gemini 优化音乐提示词 + 生成歌词"""
        
        style_name = self.STYLE_MAP.get(request.style, request.style)
        vocal_desc = {
            "auto": "auto-select vocal type",
            "male": "male vocals",
            "female": "female vocals",
            "instrumental": "no vocals, instrumental only"
        }.get(request.vocal_type, "auto")
        
        structure_desc = ""
        if request.structure:
            try:
                import json
                struct = json.loads(request.structure) if isinstance(request.structure, str) else request.structure
                structure_desc = f"\nSong structure: {', '.join(struct.get('sections', []))}"
            except Exception:
                pass
        
        lyrics_instruction = ""
        if request.lyrics:
            lyrics_instruction = f"\nUse these lyrics:\n{request.lyrics}"
        elif request.vocal_type != "instrumental":
            lyrics_instruction = "\nGenerate suitable lyrics with verse-chorus structure."
        
        prompt = f"""You are a professional music producer. Optimize this music generation prompt and generate lyrics.

Original prompt: "{request.prompt}"
Style: {style_name}
Duration: {request.duration} seconds
Type: {request.type}
Vocal: {vocal_desc}
Weirdness: {request.weirdness:.1f} (0=standard, 1=experimental)
Style strength: {request.style_strength:.1f}{structure_desc}{lyrics_instruction}

Respond as JSON:
{{
  "optimized_prompt": "detailed 2-3 sentence prompt",
  "style_suggestions": ["tag1", "tag2", "tag3"],
  "lyrics": "full lyrics with [Verse], [Chorus], [Bridge] markers"
}}"""
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.API_ENDPOINT,
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.6 + request.weirdness * 0.4,
                            "topK": 40,
                            "topP": 0.95,
                        }
                    },
                    params={"key": self.API_KEY}
                )
                response.raise_for_status()
                data = response.json()
                
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                
                import json as json_mod
                import re
                json_match = re.search(r'\{[^]*\}', text, re.DOTALL)
                if json_match:
                    result = json_mod.loads(json_match.group())
                    return (
                        result.get("optimized_prompt", request.prompt),
                        result.get("style_suggestions", []),
                        result.get("lyrics")
                    )
                return request.prompt, [], None
                
        except Exception:
            return request.prompt, [], None
    
    async def get_styles(self) -> list:
        """获取支持的音乐风格"""
        return [
            {"value": "pop", "label": "流行"},
            {"value": "rock", "label": "摇滚"},
            {"value": "electronic", "label": "电子"},
            {"value": "hip-hop", "label": "嘻哈"},
            {"value": "r&b", "label": "R&B"},
            {"value": "jazz", "label": "爵士"},
            {"value": "classical", "label": "古典"},
            {"value": "ambient", "label": "氛围"},
            {"value": "cinematic", "label": "电影配乐"},
            {"value": "lo-fi", "label": "Lo-Fi"},
        ]


# 全局服务实例
gemini_service = GeminiService()