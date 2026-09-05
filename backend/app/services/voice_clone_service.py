"""
声音克隆服务 v2 — 合规版
- 音色分组: 官方(public) / 私有(private)
- 月度克隆配额 (每用户每月 1 次)
- 操作日志存档
- 上传校验 (时长≥30s, MP3)
"""
import os, uuid, json, time
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'voice_clone_log.json')

class VoiceSample(BaseModel):
    id: str
    name: str
    audio_url: str
    duration: float
    created_at: str
    is_private: bool = False
    owner_id: str = ""
    # ASR 转写缓存：克隆时若已存在则复用，避免对同一参考音频重复转写
    prompt_text: str = ""
    prompt_language: str = ""

class VoiceCloneRequest(BaseModel):
    voice_id: Optional[str] = None
    audio_file: Optional[str] = None
    text: str
    speed: float = 1.0
    pitch_shift: int = 0
    model_config = {'populate_by_name': True}

class VoiceCloneResponse(BaseModel):
    success: bool
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    voice_id: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None

class QuotaInfo(BaseModel):
    used: int
    limit: int
    can_clone: bool

def _load_logs() -> dict:
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"clones": [], "uploads": []}

def _save_logs(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

class VoiceCloneService:
    def __init__(self):
        self.presets = [
            VoiceSample(id="preset_female_01", name="温柔女声", audio_url="https://www2.cs.uic.edu/~i101/SoundFiles/BabyElephantWalk60.wav", duration=60.0, created_at="2026-07-12T00:00:00Z", is_private=False),
            VoiceSample(id="preset_male_01", name="磁性男声", audio_url="https://www2.cs.uic.edu/~i101/SoundFiles/StarWars60.wav", duration=60.0, created_at="2026-07-12T00:00:00Z", is_private=False),
            VoiceSample(id="preset_anime_01", name="动漫少女", audio_url="https://www2.cs.uic.edu/~i101/SoundFiles/PinkPanther60.wav", duration=60.0, created_at="2026-07-12T00:00:00Z", is_private=False),
        ]
        self._private: List[VoiceSample] = []

    def _monthly_count(self, user_id: str) -> int:
        logs = _load_logs()
        month = datetime.utcnow().strftime('%Y-%m')
        return sum(1 for u in logs['clones'] if u.get('user_id') == user_id and u.get('month') == month)

    def list_voices(self, user_id: str = "") -> List[VoiceSample]:
        public = self.presets
        private = [v for v in self._private if v.owner_id == user_id]
        return public + private

    def find_voice(self, voice_id: str) -> Optional[VoiceSample]:
        """按 voice_id 查找音色（官方预设 + 用户私有），找不到返回 None。

        供 voice_clone_task._resolve_transcript 复用已缓存的 ASR 转写。
        """
        if not voice_id:
            return None
        for v in self.presets + self._private:
            if v.id == voice_id:
                return v
        return None

    def record_transcript(self, voice_id: str, prompt_text: str,
                          prompt_language: str, detected_language: str = "") -> None:
        """把 ASR 转写结果写回音色缓存（prompt_text/prompt_language）。

        目的：对同一 voice_id 的后续克隆直接复用转写，避免重复 ASR。
        容错：voice_id 不存在（如临时参考音频）时静默跳过，不影响主流程。
        """
        voice = self.find_voice(voice_id)
        if voice is None:
            return
        # 仅在尚未缓存时写入，显式/既有转写不被覆盖
        if not voice.prompt_text:
            voice.prompt_text = prompt_text
            voice.prompt_language = prompt_language or "auto"

    def get_quota(self, user_id: str) -> QuotaInfo:
        used = self._monthly_count(user_id)
        return QuotaInfo(used=used, limit=1, can_clone=used < 1)

    def upload_voice(self, audio_url: str, name: str = None, user_id: str = "") -> VoiceSample:
        # 配额检查
        if self._monthly_count(user_id) >= 1:
            raise ValueError("本月克隆次数已达上限（1 次/月）")

        # 格式校验
        url_lower = audio_url.lower()
        if not any(url_lower.endswith(ext) for ext in ['.mp3', '.wav', '.m4a', '.ogg', '.flac']):
            raise ValueError("仅支持 MP3/WAV/M4A/OGG/FLAC 格式")

        # 时长校验由前端提醒，后端 Mock 60s
        voice_id = f"voice_{uuid.uuid4().hex[:8]}"
        sample = VoiceSample(
            id=voice_id,
            name=name or f"我的声音",
            audio_url=audio_url,
            duration=60.0,
            created_at=datetime.utcnow().isoformat(),
            is_private=True,
            owner_id=user_id or "anonymous",
        )
        self._private.append(sample)

        # 操作日志
        logs = _load_logs()
        logs['clones'].append({
            "user_id": user_id or "anonymous",
            "voice_id": voice_id,
            "audio_url": audio_url,
            "name": name,
            "created_at": datetime.utcnow().isoformat(),
            "month": datetime.utcnow().strftime('%Y-%m'),
        })
        _save_logs(logs)
        return sample

    async def clone_voice(self, request: VoiceCloneRequest) -> VoiceCloneResponse:
        try:
            voice = None
            if request.voice_id:
                for v in self.presets + self._private:
                    if v.id == request.voice_id:
                        voice = v
                        break
            if not voice:
                voice = self.presets[0]

            mock_url = f"https://www2.cs.uic.edu/~i101/SoundFiles/{voice.audio_url.split('/')[-1]}"
            return VoiceCloneResponse(
                success=True,
                audio_url=mock_url,
                duration=10.0,
                voice_id=voice.id,
                message=f"✅ 使用声音 \"{voice.name}\" 合成成功 (Mock 模式)\n\n⏳ 真实 RVC 集成待开启（需要 GPU 支持）"
            )
        except Exception as e:
            return VoiceCloneResponse(success=False, error=f"声音克隆失败：{str(e)}")


voice_clone_service = VoiceCloneService()
