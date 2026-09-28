"""P6-B-C3-5-D：delete_user_task 的 R2 删除键必须精确来自 download manifest。

契约（本轮新增，均为最小回归）：
- D1  manifest（task_store.get 解析后的 dict）的 values 即真实 R2 key，按原样逐个删除。
- D2  不再出现硬编码 music/{tid}/full_mp3.mp3，也不再用 volume_files 文件名重建 key。
- D3  源码里不再对已解析的 manifest dict 调用 json.loads。
- D4  parts（music/{tid}_part1|_part2/...）不在 manifest 内，绝不被删除（C3-5-B 冻结）。

无任何真实外呼：boto3.client / r2_config 全部替换为替身；DB 用临时 SQLite。
"""

import asyncio
import inspect

import pytest

from app.routers import ai_music
from app.services import r2_config, task_store

USER = "u-c35d"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(task_store, "_DB_PATH", str(tmp_path / "c35d.db"))
    return tmp_path


@pytest.fixture()
def fake_s3(monkeypatch):
    import boto3

    deleted = []

    class _S3:
        def delete_object(self, Bucket, Key):
            deleted.append(Key)
            return {}

    monkeypatch.setattr(boto3, "client", lambda *a, **k: _S3())
    monkeypatch.setattr(r2_config, "get_r2_account_id", lambda: "acct")
    monkeypatch.setattr(r2_config, "get_r2_access_key", lambda: "ak")
    monkeypatch.setattr(r2_config, "get_r2_secret_key", lambda: "sk")
    monkeypatch.setattr(r2_config, "get_r2_bucket", lambda: "bucket")
    return deleted


def _mk_task(task_id: str, download: dict, volume_files: dict | None = None) -> str:
    task_store.new_task(user_key=USER, task_id=task_id)
    task_store.update(
        task_id,
        state="completed",
        download=download,
        volume_files=volume_files or {},
        audio_url="https://cdn.example/x",
    )
    return task_id


def _delete(task_id: str, user_id: str = USER):
    return asyncio.run(ai_music.delete_user_task(task_id, user_id=user_id))


def test_d1_manifest_keys_deleted_exactly(env, fake_s3):
    _mk_task(
        "T1",
        {"full": "music/T1/full_mp3.wav", "full_wav": "music/T1/full_wav.wav"},
    )
    resp = _delete("T1")
    assert resp == {"success": True, "detail": "任务删除成功"}
    # 恰好 manifest 的两个值，顺序即 manifest 插入顺序
    assert fake_s3 == ["music/T1/full_mp3.wav", "music/T1/full_wav.wav"]
    assert task_store.get("T1") is None, "R2 全部成功后 DB 记录必须删除（既有语义保留）"


def test_d2_no_hardcoded_mp3_or_volume_files_reconstruction(env, fake_s3):
    _mk_task(
        "T2",
        {"full": "music/T2/full_mp3.wav", "full_wav": "music/T2/full_wav.wav"},
        volume_files={
            "full_wav": "xyz_combined_300s.wav",
            "vocals": "T2_vocals_original_name.wav",
        },
    )
    _delete("T2")
    assert "music/T2/full_mp3.mp3" not in fake_s3, "硬编码 .mp3 key 是死代码，不得复活"
    assert not any("combined" in k for k in fake_s3), "不得用 volume_files 重建 combined key"
    assert not any("original_name" in k for k in fake_s3), "volume_files 文件名不是 R2 key"
    assert fake_s3 == ["music/T2/full_mp3.wav", "music/T2/full_wav.wav"]


def test_d3_source_has_no_json_loads_on_parsed_manifest():
    src = inspect.getsource(ai_music.delete_user_task)
    # 只看代码行：注释/说明允许提及 json.loads，代码本身绝不能调用
    code_only = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    assert "json.loads" not in code_only, (
        "manifest 已由 task_store.get 解析为 dict，禁止二次 json.loads"
    )


def test_d4_part_keys_never_deleted(env, fake_s3):
    _mk_task("T3", {"full_wav": "music/T3/full_wav.wav"})
    _delete("T3")
    assert fake_s3 == ["music/T3/full_wav.wav"]
    assert not any("_part1" in k or "_part2" in k for k in fake_s3), (
        "parts 不在 download manifest 内，本轮（C3-5-B 冻结）绝不删除"
    )
