import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _quota_stub():
    """stub ai_limits.reserve/refund，避免真实 quota 副作用。"""
    from app.services import ai_limits
    with patch.object(ai_limits, "reserve_generation", return_value={"success": True}) as _res, \
         patch.object(ai_limits, "refund_generation", return_value={"success": True}) as _ref:
        yield {"reserve": _res, "refund": _ref}


@pytest.fixture(autouse=True)
def _jwt_stub(monkeypatch):
    """Phase 3B-4A：身份改为 Authorization Bearer JWT。打桩 resolve_auth_user_id。"""
    from app.services import auth_identity

    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):] or None
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


def test_separate_audio_success(_quota_stub):
    # Mock demucs_service.separate to return fake local stems
    fake_stems = [
        os.path.join(tempfile.gettempdir(), "stem1.wav"),
        os.path.join(tempfile.gettempdir(), "stem2.wav"),
        os.path.join(tempfile.gettempdir(), "stem3.wav"),
        os.path.join(tempfile.gettempdir(), "stem4.wav"),
    ]
    # Create dummy files
    for p in fake_stems:
        Path(p).touch()
    
    with patch('app.services.audio_separation_service.demucs_service.separate') as mock_separate, \
         patch('app.services.cdn_uploader.cdn_uploader.upload_audio', new_callable=AsyncMock) as mock_upload:
        
        mock_separate.return_value = {
            "success": True,
            "stems": fake_stems,
            "duration": 12.5,
            "message": "分离成功"
        }
        
        mock_upload.side_effect = lambda path, content_type: f"https://cdn.example.com/{Path(path).name}"
        
        # Prepare file upload
        test_file_content = b"fake wav content"
        files = {"file": ("test.wav", test_file_content, "audio/wav")}
        data = {"model": "htdemucs"}
        
        response = client.post("/api/v1/audio/separate", files=files, data=data,
                               headers={"Authorization": "Bearer u1"})
        
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] == True
        assert len(json_data["stems"]) == 4
        for url in json_data["stems"]:
            assert url.startswith("https://cdn.example.com/")
        assert json_data["duration"] == 12.5
        assert "分离成功" in json_data["message"]
        
        # Verify mocks called
        mock_separate.assert_called_once()
        args, kwargs = mock_separate.call_args
        assert args[0] == str(Path(tempfile.gettempdir()) / "audio_uploads" / "test.wav")
        assert kwargs.get("model") == "htdemucs"
        assert mock_upload.call_count == 4
        
        # Cleanup dummy files
        for p in fake_stems:
            try:
                Path(p).unlink()
            except:
                pass

def test_separate_audio_failure():
    with patch('app.services.audio_separation_service.demucs_service.separate') as mock_separate:
        mock_separate.return_value = {
            "success": False,
            "stems": [],
            "duration": 0,
            "message": "内部错误"
        }
        
        test_file_content = b"fake wav content"
        files = {"file": ("test.wav", test_file_content, "audio/wav")}
        data = {"model": "htdemucs"}
        
        response = client.post("/api/v1/audio/separate", files=files, data=data,
                               headers={"Authorization": "Bearer u1"})
        
        assert response.status_code == 200  # endpoint returns 200 with success=False
        json_data = response.json()
        assert json_data["success"] == False
        assert json_data["stems"] == []
        assert json_data["duration"] == 0
        assert "内部错误" in json_data["message"]
        
        mock_separate.assert_called_once()

def test_separate_audio_upload_failure():
    fake_stems = [os.path.join(tempfile.gettempdir(), "stem1.wav")]
    Path(fake_stems[0]).touch()
    
    with patch('app.services.audio_separation_service.demucs_service.separate') as mock_separate, \
         patch('app.services.cdn_uploader.cdn_uploader.upload_audio', new_callable=AsyncMock) as mock_upload:
        
        mock_separate.return_value = {
            "success": True,
            "stems": fake_stems,
            "duration": 5.0,
            "message": "OK"
        }
        
        mock_upload.side_effect = Exception("CDN error")
        
        test_file_content = b"fake wav content"
        files = {"file": ("test.wav", test_file_content, "audio/wav")}
        data = {"model": "htdemucs"}
        
        response = client.post("/api/v1/audio/separate", files=files, data=data,
                               headers={"Authorization": "Bearer u1"})
        
        # Should return 500 error
        assert response.status_code == 500
        json_data = response.json()
        assert json_data["detail"] == "CDN 上传失败: CDN error"
        
        # Cleanup
        try:
            Path(fake_stems[0]).unlink()
        except:
            pass