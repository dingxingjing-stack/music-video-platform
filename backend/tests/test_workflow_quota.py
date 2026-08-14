import os
import time
import pytest
import asyncio
import tempfile
from fastapi.testclient import TestClient
from unittest.mock import patch

# Import the app
from main import app
from app.services import ai_limits, task_store, workflow_router

client = TestClient(app)

# Minimal valid payload for each workflow endpoint
ENDPOINT_PAYLOADS = {
    '/a': {'prompt': 'test prompt'},
    '/b': {'prompt': 'test prompt', 'tts_text': 'test tts'},
    '/c': {'audio_base64': 'dGVzdCBhdWRpbyBkYXRh'},  # base64 of 'test audio data'
    '/d': {'midi_project': {'name': 'test', 'tracks': []}},
}


class _FakeEngine:
    """Deterministic engine stub. Avoids real inference services / GPU entirely."""

    def __init__(self, fail: bool = False):
        self.fail = fail

    async def run_path_a(self, task_id, *args, **kwargs):
        if self.fail:
            raise RuntimeError("simulated failure")

    async def run_path_b(self, task_id, *args, **kwargs):
        if self.fail:
            raise RuntimeError("simulated failure")

    async def run_path_c(self, task_id, *args, **kwargs):
        if self.fail:
            raise RuntimeError("simulated failure")

    async def run_path_d(self, task_id, *args, **kwargs):
        if self.fail:
            raise RuntimeError("simulated failure")


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset in-process stores and engine between tests so tests are order-independent."""
    task_store._TASKS.clear()
    task_store._USER_LOCKS.clear()
    workflow_router._WORKFLOW_ENGINE = None
    yield
    task_store._TASKS.clear()
    task_store._USER_LOCKS.clear()
    workflow_router._WORKFLOW_ENGINE = None


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Each test uses an isolated SQLite database to avoid polluting backend/data/beta.db."""
    db_path = str(tmp_path / 'test_beta.db')
    monkeypatch.setattr(ai_limits, '_DB_DIR', str(tmp_path))
    monkeypatch.setattr(ai_limits, '_DB_PATH', db_path)
    return db_path


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", sorted(ENDPOINT_PAYLOADS))
async def test_workflow_mock_mode_no_quota_consumption(isolated_db, monkeypatch, endpoint):
    '''In mock mode, workflow endpoints should not consume quota.'''
    monkeypatch.setenv('WORKFLOW_MODE', 'mock')
    monkeypatch.setattr(workflow_router, '_get_workflow_engine', lambda: _FakeEngine(fail=False))
    user_key = f'mock_test_user_{endpoint[1:]}'
    usage_before = await ai_limits.generation_usage_status(user_key)
    response = client.post(
        f'/api/v1/workflow{endpoint}',
        headers={'X-User-ID': user_key},
        json=ENDPOINT_PAYLOADS[endpoint]
    )
    assert response.status_code == 200, response.text
    usage_after = await ai_limits.generation_usage_status(user_key)
    assert usage_before == usage_after


@pytest.mark.parametrize("endpoint", sorted(ENDPOINT_PAYLOADS))
def test_workflow_real_mode_quota_failure_returns_429(isolated_db, monkeypatch, endpoint):
    '''In real mode, workflow endpoints return 429 when daily quota is exhausted.'''
    monkeypatch.setenv('WORKFLOW_MODE', 'real')
    monkeypatch.setattr(ai_limits, 'DAILY_GENERATION_LIMIT', 1)
    user_key = f'real_429_{endpoint[1:]}'
    result = ai_limits.reserve_generation(user_key)
    assert result['success'], f'Failed to reserve generation: {result}'
    response = client.post(
        f'/api/v1/workflow{endpoint}',
        headers={'X-User-ID': user_key},
        json=ENDPOINT_PAYLOADS[endpoint]
    )
    assert response.status_code == 429, response.text
    detail = response.json()['detail']
    assert isinstance(detail, str) and len(detail) > 0
    ai_limits.refund_generation(user_key)


@pytest.mark.parametrize("endpoint", sorted(ENDPOINT_PAYLOADS))
def test_workflow_real_mode_success_and_refund_on_failure(isolated_db, monkeypatch, endpoint):
    '''In real mode, task starts (200); on background failure the daily/monthly quota is refunded,
    while global_usage is NOT refunded.'''
    monkeypatch.setenv('WORKFLOW_MODE', 'real')
    monkeypatch.setattr(ai_limits, 'DAILY_GENERATION_LIMIT', 1)
    monkeypatch.setattr(workflow_router, '_get_workflow_engine', lambda: _FakeEngine(fail=True))
    user_key = f'real_refund_{endpoint[1:]}'

    response = client.post(
        f'/api/v1/workflow{endpoint}',
        headers={'X-User-ID': user_key},
        json=ENDPOINT_PAYLOADS[endpoint]
    )
    assert response.status_code == 200, response.text
    task_id = response.json()['task_id']

    # global_usage must have been incremented (reserved once)
    from app.services.ai_limits import _today, _get_conn
    today = _today()
    conn = _get_conn()
    try:
        row = conn.execute('SELECT count FROM global_usage WHERE date=?', (today,)).fetchone()
        global_used = row['count'] if row else 0
        assert global_used >= 1
    finally:
        conn.close()

    # Wait for the task to fail and the quota to be refunded.
    # Refund happens in _run_workflow_async's finally after state is set to "failed",
    # so poll until a fresh reserve succeeds again (proves exactly one refund).
    timeout = 15.0
    start = time.time()
    task = None
    refund_ok = False
    while time.time() - start < timeout:
        task = task_store.get(task_id)
        if task and task.get('state') == 'failed':
            reserve_result = ai_limits.reserve_generation(user_key)
            if reserve_result['success']:
                refund_ok = True
                break
        time.sleep(0.1)
    else:
        raise AssertionError(f'Timeout waiting for task {task_id} to fail / refund')

    assert task is not None
    assert task['state'] == 'failed'
    assert refund_ok, 'Quota was not refunded after task failure'

    # No double refund: with daily limit = 1 and one usage consumed above,
    # a second reserve must fail.
    second = ai_limits.reserve_generation(user_key)
    assert not second['success'], 'Quota was refunded more than once'

    # Clean up the quota we consumed for the assertion
    ai_limits.refund_generation(user_key)
    task_store.delete(task_id)


@pytest.mark.parametrize("endpoint", sorted(ENDPOINT_PAYLOADS))
def test_workflow_real_mode_lock_failure_no_stale_task(isolated_db, monkeypatch, endpoint):
    '''When the user already has an in-flight task, the endpoint must:
    - return 429
    - NOT leave a newly created task behind
    - refund any quota it reserved'''
    monkeypatch.setenv('WORKFLOW_MODE', 'real')
    monkeypatch.setattr(ai_limits, 'DAILY_GENERATION_LIMIT', 2)
    monkeypatch.setattr(workflow_router, '_get_workflow_engine', lambda: _FakeEngine(fail=False))
    user_key = f'real_lock_{endpoint[1:]}'

    # Simulate an in-flight task holding the user's lock
    existing_tid = task_store.new_task(user_key=user_key)
    assert task_store.acquire_lock(user_key, existing_tid)

    before_count = len(task_store._TASKS)

    response = client.post(
        f'/api/v1/workflow{endpoint}',
        headers={'X-User-ID': user_key},
        json=ENDPOINT_PAYLOADS[endpoint]
    )
    assert response.status_code == 429, response.text

    # No stale task leaked from the rejected request
    assert len(task_store._TASKS) == before_count, task_store._TASKS
    # User lock is still held by the original in-flight task
    assert task_store._USER_LOCKS.get(user_key, {}).get('task_id') == existing_tid

    # Clean up
    task_store.release_lock_for_task(existing_tid)
    task_store.delete(existing_tid)