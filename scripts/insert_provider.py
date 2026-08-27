import pathlib
import sys

# Read the file
filepath = pathlib.Path(r'C:\Users\dingx\music-video-platform\backend\app\routers\ai_music.py')
data = filepath.read_text(encoding='utf-8')
lines = data.split('\n')

# Find insertion point: after line 66 (the '}' closing DOWNLOAD_FILES)
# Lines 59-66 contain DOWNLOAD_FILES dict, line 66 is '}'
# After that, lines 67-68 are blank, line 69 starts async def

insert_idx = 66  # Fallback insertion index after the '}' line

# The new Provider Registry code to insert (as text)
new_code = '''# Provider Registry
_provider_registry = None

async def get_provider_registry():
    global _provider_registry
    if _provider_registry is None:
        from app.services.provider_registry import ProviderRegistry
        _provider_registry = ProviderRegistry()
        
        # HeartMuLa Provider
        try:
            heartmula_service = get_heartmula_service()
            if heartmula_service:
                from app.services.provider_registry import BaseProvider
                class HeartMuLaProviderImpl:
                    @property
                    def name(self): return "heartmula"
                    @property
                    def provider_type(self): return "heartmula"
                    @property
                    def capabilities(self): return ["text_to_music", "lyrics_to_music"]
                    @property
                    def max_duration(self): return 300
                    async def generate(self, request: dict) -> dict:
                        from app.services.heartmula_service import HeartMuLaRequest, get_heartmula_service
                        svc = get_heartmula_service()
                        if not svc:
                            return {"success": False, "error": "HeartMuLa service not available"}
                        from app.services.heartmula_service import HeartMuLaRequest
                        result = await get_heartmula_service().generate_music(HeartMuLaRequest(**request))
                        return {"success": result.get("success", False), "audio_url": result.get("audio_url"), "duration": result.get("duration"), "error": result.get("error"), "task_id": result.get("task_id")}
                    async def health_check(self) -> dict:
                        return {"healthy": True, "provider": "heartmula"}
                _provider_registry.register(HeartMuLaProviderImpl())
        except Exception as e:
            print(f"[Provider] HeartMuLa registration failed: {e}")
        
        # HeartCodec - 后处理编解码
        try:
            from app.services.heartcodec_service import get_heartcodec_service
            heartcodec_service = get_heartcodec_service()
            if heartcodec_service:
                from app.services.provider_registry import BaseProvider
                class HeartCodecProviderImpl:
                    @property
                    def name(self): return "heartcodec"
                    @property
                    def provider_type(self): return "heartcodec"
                    @property
                    def capabilities(self): return ["audio_encoding", "audio_decoding", "audio_transcode"]
                    @property
                    def max_duration(self): return 600
                    async def generate(self, request: dict) -> dict:
                        return {"success": False, "error": "HeartCodec is post-processor only"}
                    async def health_check(self) -> dict:
                        return {"healthy": True, "provider": "heartcodec"}
                _provider_registry.register(HeartCodecProvider())
        except Exception as e:
            print(f"[Provider] HeartCodec registration failed: {e}")
        
        # ACE-Step Provider
        try:
            from app.services.ace_step_client import generate_full_song as ace_step_generate
            from app.services.ace_step_client import QueueFullError
            class ACEStepProvider:
                @property
                def name(self): return "ace_step"
                @property
                def provider_type(self): return "ace_step"
                @property
                def capabilities(self): return ["text_to_music", "lyrics_to_music", "stem_separation"]
                @property
                def max_duration(self): return 300
                async def generate(self, request: dict) -> dict:
                    try:
                        result = await ace_step_generate(
                            prompt=request.get("prompt", ""),
                            lyrics=request.get("lyrics", ""),
                            duration=request.get("duration", 180)
                        )
                        if result:
                            return {"success": True, "audio_url": None, "volume_files": result, "provider": "ace_step"}
                        return {"success": False, "error": "ACE-Step generation failed"}
                    except Exception as e:
                        return {"success": False, "error": str(e)}
                async def health_check(self) -> dict:
                    return {"healthy": True, "provider": "ace_step"}
            _provider_registry.register(ACEStepProvider())
        except Exception as e:
            print(f"[Provider] ACE-Step registration failed: {e}")
        
        # HF ACE-Step Provider
        try:
            from app.services.hf_music_service import HFMusicService, HFModel
            hf_service = HFMusicService()
            class HFACEProvider:
                @property
                def name(self): return "hf_ace_step"
                @property
                def provider_type(self): return "hf_ace_step"
                @property
                def capabilities(self): return ["text_to_music", "lyrics_to_music"]
                @property
                def max_duration(self): return 120
                async def generate(self, request: dict) -> dict:
                    try:
                        from app.services.hf_music_service import HFModel
                        result = await hf_service.generate_song(
                            lyrics=request.get("lyrics", request.get("prompt", "")),
                            model=HFModel.ACE_STEP,
                            style=request.get("style", "pop"),
                            duration=request.get("duration", 180)
                        )
                        return {"success": result.success, "audio_url": result.audio_url, "error": result.error, "task_id": result.task_id}
                    except Exception as e:
                        return {"success": False, "error": str(e)}
                async def health_check(self) -> dict:
                    from app.services.hf_music_service import HFModel
                    return await hf_service.check_health(HFModel.ACE_STEP)
            _provider_registry.register(HFACEProvider())
        except Exception as e:
            print(f"[Provider] HF ACE-Step registration failed: {e}")
        
        # Mock Provider
        class MockProvider:
            @property
            def name(self): return "mock"
            @property
            def provider_type(self): return "mock"
            @property
            def capabilities(self): return ["text_to_music", "mock"]
            @property
            def max_duration(self): return 300
            async def generate(self, request: dict) -> dict:
                return {"success": True, "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", "duration": 30}
            async def health_check(self) -> dict:
                return {"healthy": True, "provider": "mock"}
            _provider_registry.register(MockProvider())
        
        # Fallback chain
        _provider_registry.set_fallback_chain("heartmula", ["ace_step", "hf_ace_step", "mock"])
        _provider_registry.set_fallback_chain("ace_step", ["hf_ace_step", "mock"])
        _provider_registry.set_fallback_chain("hf_ace_step", ["mock"])
        
        print("[Provider] Registry initialized with providers:", list(_provider_registry._providers.keys()))
    
    return _provider_registry


'''

# Insert the new code after line 66 (index 66 in 1-indexed, which is lines[:66] + new_code + lines[66:])
# lines[:66] gives first 66 elements (indices 0-65), which includes line 66 ('}') at 0-indexed position 65
# lines[66:] gives elements from index 66 onward, which is line 67 onward (1-indexed)

# But wait - if line 66 ('}') is at 1-indexed position 66, that's 0-indexed position 65.
# lines[:66] = elements at indices 0,1,...,65 = first 66 elements = lines 1-66 (1-indexed).
# So lines[:66] includes the '}' at 1-indexed line 66.

# lines[66:] = elements at indices 66,67,... = lines 67 onward (1-indexed).
# That includes the blank lines and async def.

# So new_lines = lines[:66] + [new_code] + lines[66:] should insert after line 66 ('}').

new_lines = lines[:66] + [new_code] + lines[66:]
new_data = '\n'.join(new_lines)

# Write the file
filepath.write_text(new_data, encoding='utf-8')

print('Provider Registry inserted successfully!')
print(f'Total lines after insertion: {len(new_lines)}')

# Verify the insertion by checking lines around the insertion point
print('\\nVerification - lines around insertion point:')
for i in range(58, min(80, len(new_lines))):
    print(f'  {i+1}: {new_lines[i]}')