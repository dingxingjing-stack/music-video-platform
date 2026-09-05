"""测试：Beta 灰度服务核心逻辑 + NULL 值处理 + consume_credit 并发原子扣额度。"""

import asyncio
import sqlite3
import pytest
from app.services import beta_service


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """每个测试使用独立 SQLite，避免污染 backend/data/beta.db。"""
    db_path = str(tmp_path / "test_beta.db")
    monkeypatch.setattr(beta_service, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(beta_service, "DB_PATH", db_path)
    # 初始化数据库 - 使用测试覆盖路径创建表
    beta_service._init_db()
    return db_path


class TestBetaServiceNullHandling:
    """测试 NULL 值处理，确保不会抛出 TypeError: '>=' not supported between instances of 'NoneType' and 'int'"""

    @pytest.mark.asyncio
    async def test_check_gray_status_with_all_nulls(self, isolated_db):
        """activity_score、total_generations、daily_credits_used、daily_credits_limit、is_gray 全为 NULL"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, NULL, NULL, NULL, NULL, NULL)
        """, ("null_user_all",))
        conn.commit()
        conn.close()

        result = await beta_service.check_gray_status("null_user_all")

        assert result["user_id"] == "null_user_all"
        assert result["is_gray"] is False
        assert result["daily_credits_used"] == 0
        assert result["daily_credits_limit"] == beta_service.DAILY_LIMIT_NORMAL
        assert result["total_generations"] == 0
        assert result["activity_score"] == 0
        assert result["can_apply"] is False

    @pytest.mark.asyncio
    async def test_check_gray_status_with_partial_nulls(self, isolated_db):
        """部分字段为 NULL"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, 0, 5, NULL, 10, NULL)
        """, ("null_user_partial",))
        conn.commit()
        conn.close()

        result = await beta_service.check_gray_status("null_user_partial")

        assert result["user_id"] == "null_user_partial"
        assert result["is_gray"] is False
        assert result["daily_credits_used"] == 5
        assert result["daily_credits_limit"] == beta_service.DAILY_LIMIT_NORMAL  # NULL -> 默认值
        assert result["total_generations"] == 10
        assert result["activity_score"] == 0  # NULL -> 0
        assert result["can_apply"] is False  # activity_score=0 < 100

    @pytest.mark.asyncio
    async def test_consume_credit_with_nulls(self, isolated_db):
        """consume_credit 处理 NULL 值"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, NULL, NULL, NULL, NULL, NULL)
        """, ("null_consume_user",))
        conn.commit()
        conn.close()

        result = await beta_service.consume_credit("null_consume_user", amount=2)

        assert result["success"] is True
        assert result["used_today"] == 2
        assert result["limit"] == beta_service.DAILY_LIMIT_NORMAL
        assert result["remaining"] == beta_service.DAILY_LIMIT_NORMAL - 2

        # 验证数据库已更新
        status = await beta_service.check_gray_status("null_consume_user")
        assert status["daily_credits_used"] == 2
        assert status["total_generations"] == 1
        assert status["activity_score"] == 2

    @pytest.mark.asyncio
    async def test_get_feature_access_with_nulls(self, isolated_db):
        """get_feature_access 处理 NULL 值"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, NULL, NULL, NULL, NULL, NULL)
        """, ("null_feature_user",))
        conn.commit()
        conn.close()

        result = await beta_service.get_feature_access("null_feature_user")

        assert result["user_id"] == "null_feature_user"
        assert result["is_gray"] is False
        assert "features" in result
        # 灰度功能不可访问
        assert result["features"]["mv_generate"]["accessible"] is False
        assert result["features"]["ws_collab"]["accessible"] is False
        # 开放功能可访问
        assert result["features"]["mureka_generate"]["accessible"] is True

    @pytest.mark.asyncio
    async def test_daily_reset_with_nulls(self, isolated_db):
        """daily_reset 处理 NULL 值"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, 0, 5, 10, 10, 20)
        """, ("reset_user1",))
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, NULL, NULL, NULL, NULL, NULL)
        """, ("reset_user2",))
        conn.commit()
        conn.close()

        result = await beta_service.daily_reset()

        assert result["success"] is True
        assert result["message"] == "每日额度已重置，影响 1 个用户"  # 只有 reset_user1 有 used > 0

        # 验证 reset_user1 被重置
        status1 = await beta_service.check_gray_status("reset_user1")
        assert status1["daily_credits_used"] == 0

        # 验证 reset_user2 保持为 0（NULL 视为 0）
        status2 = await beta_service.check_gray_status("reset_user2")
        assert status2["daily_credits_used"] == 0


class TestBetaServiceCoreLogic:
    """测试核心业务逻辑，确保修复后不改变原有行为"""

    @pytest.mark.asyncio
    async def test_new_user_defaults(self, isolated_db):
        """新用户自动获得默认值"""
        result = await beta_service.check_gray_status("new_user")
        assert result["is_gray"] is False
        assert result["daily_credits_used"] == 0
        assert result["daily_credits_limit"] == beta_service.DAILY_LIMIT_NORMAL
        assert result["total_generations"] == 0
        assert result["activity_score"] == 0
        assert result["can_apply"] is False

    @pytest.mark.asyncio
    async def test_can_apply_logic(self, isolated_db):
        """测试灰度申请资格判断逻辑"""
        # 情况 1: 已是灰度用户 -> 不能申请
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, activity_score, total_generations)
            VALUES (?, 1, 200, 100)
        """, ("gray_user",))
        conn.commit()
        conn.close()

        result = await beta_service.check_gray_status("gray_user")
        assert result["is_gray"] is True
        assert result["can_apply"] is False  # 已是灰度用户

        # 情况 2: 非灰度，但分数不够 -> 不能申请
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, activity_score, total_generations)
            VALUES (?, 0, 50, 60)
        """, ("low_score_user",))
        conn.commit()
        conn.close()

        result = await beta_service.check_gray_status("low_score_user")
        assert result["is_gray"] is False
        assert result["can_apply"] is False  # activity_score < 100

        # 情况 3: 非灰度，activity_score 足够但 total_generations 不够 -> 不能申请
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, activity_score, total_generations)
            VALUES (?, 0, 150, 30)
        """, ("low_gens_user",))
        conn.commit()
        conn.close()

        result = await beta_service.check_gray_status("low_gens_user")
        assert result["is_gray"] is False
        assert result["can_apply"] is False  # total_generations < 50

        # 情况 4: 非灰度，两个条件都满足 -> 能申请
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, activity_score, total_generations)
            VALUES (?, 0, 150, 60)
        """, ("eligible_user",))
        conn.commit()
        conn.close()

        result = await beta_service.check_gray_status("eligible_user")
        assert result["is_gray"] is False
        assert result["can_apply"] is True

    @pytest.mark.asyncio
    async def test_auto_gray_promotion(self, isolated_db):
        """测试自动灰度升级"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, 0, 0, 10, 49, 98)
        """, ("promo_user",))
        conn.commit()
        conn.close()

        # 消费一次，触发阈值检查
        result = await beta_service.consume_credit("promo_user", amount=1)
        assert result["success"] is True

        # 验证自动升级
        status = await beta_service.check_gray_status("promo_user")
        assert status["is_gray"] is True
        assert status["daily_credits_limit"] == beta_service.DAILY_LIMIT_GRAY
        assert status["total_generations"] == 50
        assert status["activity_score"] == 100

    @pytest.mark.asyncio
    async def test_apply_gray(self, isolated_db):
        """测试灰度申请提交"""
        result = await beta_service.apply_gray("apply_user", "需要 MV 生成功能", "test@example.com", "mv_generate")

        assert result["success"] is True
        assert "申请已提交" in result["message"]

        # 验证数据库记录 - 通过服务层验证，避免直接 SQL 读取的 schema 差异
        conn = sqlite3.connect(isolated_db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT user_id, reason, contact, feature_key FROM beta_gray_applications WHERE user_id=?", ("apply_user",)).fetchone()
        conn.close()

        assert row is not None
        assert row["user_id"] == "apply_user"
        assert row["reason"] == "需要 MV 生成功能"
        assert row["contact"] == "test@example.com"
        assert row["feature_key"] == "mv_generate"

    @pytest.mark.asyncio
    async def test_consume_credit_success(self, isolated_db):
        """正常消费递增 used 并递增 total_generations / activity_score"""
        result = await beta_service.consume_credit("consume_ok", amount=1)
        assert result["success"] is True
        assert result["used_today"] == 1
        assert result["limit"] == beta_service.DAILY_LIMIT_NORMAL
        status = await beta_service.check_gray_status("consume_ok")
        assert status["total_generations"] == 1
        assert status["activity_score"] == 2

    @pytest.mark.asyncio
    async def test_consume_credit_over_limit(self, isolated_db):
        """额度耗尽时原子更新拒绝"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit)
            VALUES (?, 0, 10, 10)
        """, ("limit_user",))
        conn.commit()
        conn.close()

        result = await beta_service.consume_credit("limit_user", amount=1)
        assert result["success"] is False
        assert "今日额度已用完" in result["message"]

    @pytest.mark.asyncio
    async def test_consume_credit_gray_user_higher_limit(self, isolated_db):
        """灰度用户有更高额度"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit)
            VALUES (?, 1, 25, 30)
        """, ("gray_limit_user",))
        conn.commit()
        conn.close()

        # 普通用户额度 10，灰度用户 30
        # used=25, limit=30, consume 5 -> used_today=30, remaining=0
        result = await beta_service.consume_credit("gray_limit_user", amount=5)
        assert result["success"] is True
        assert result["limit"] == 30
        assert result["used_today"] == 30
        assert result["remaining"] == 0


class TestBetaServiceConsumeAtomicity:
    """测试 consume_credit 的原子条件更新行为"""

    @pytest.mark.asyncio
    async def test_consume_does_not_exceed_limit_concurrently(self, isolated_db):
        """高并发下累计消费不能超过 limit（原子条件更新 + rowcount 判定）"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score)
            VALUES (?, 0, 0, 3, 0, 0)
        """, ("atomic_user",))
        conn.commit()
        conn.close()

        results = await asyncio.gather(
            *[beta_service.consume_credit("atomic_user", amount=1) for _ in range(5)]
        )
        successes = [r for r in results if r.get("success")]
        # limit=3，最多成功 3 次，第 4、5 次必须被原子条件拒绝
        assert len(successes) == 3
        final = await beta_service.check_gray_status("atomic_user")
        assert final["daily_credits_used"] == 3

    @pytest.mark.asyncio
    async def test_consume_does_not_go_negative_or_rollback(self, isolated_db):
        """并发超额消费不会导致 used 超过 limit，也不会因竞态回退"""
        conn = sqlite3.connect(isolated_db)
        conn.execute("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit)
            VALUES (?, 0, 0, 1)
        """, ("atomic_one",))
        conn.commit()
        conn.close()
        results = await asyncio.gather(
            *[beta_service.consume_credit("atomic_one", amount=1) for _ in range(4)]
        )
        assert len([r for r in results if r.get("success")]) == 1
        final = await beta_service.check_gray_status("atomic_one")
        assert final["daily_credits_used"] == 1
        assert final["daily_credits_used"] <= final["daily_credits_limit"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])