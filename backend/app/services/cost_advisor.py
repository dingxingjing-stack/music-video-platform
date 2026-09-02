"""
Cost Advisor MVP - Read-only cost analysis for Modal production deployment
Reads from existing data sources: Modal billing, Supabase, R2, generation_cost_logs,
generation_usage, global_usage, ai_tasks, quota (ai_limits), Modal billing API.
Outputs structured JSON report with cost breakdown, alerts, and recommendations.
"""

from __future__ import annotations
import os
import json
import sqlite3
import subprocess
import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path


@dataclass
class CostBreakdown:
    """Cost breakdown for a period"""
    period: str  # "today" or "month"
    total_cost_usd: float
    gpu_cost_usd: float
    volume_cost_usd: float
    r2_cost_usd: float
    other_cost_usd: float


@dataclass
class UsageStats:
    """Usage statistics for a period"""
    generation_count: int
    success_count: int
    failure_count: int
    failure_rate: float


@dataclass
class BudgetStatus:
    """Budget utilization status"""
    daily_limit: Optional[int]
    daily_used: int
    monthly_limit: Optional[int]
    monthly_used: int
    daily_pct: float
    monthly_pct: float
    budget_daily_limit: Optional[int]
    budget_daily_used: int
    budget_pct: float


@dataclass
class Alert:
    level: str  # "INFO", "WARNING", "CRITICAL"
    code: str
    message: str
    suggestion: str


@dataclass
class CostReport:
    """Complete cost advisor report"""
    period: str  # "today" or "month"
    total_cost_usd: float
    gpu_cost_usd: float
    volume_cost_usd: float
    r2_cost_usd: float
    generation_count: int
    failure_rate: float
    budget_usage_pct: float
    forecast_monthly_cost: float
    alerts: List[dict]
    recommendations: List[str]
    data_availability: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def get_sqlite_conn(db_path: str) -> sqlite3.Connection:
    """Get SQLite connection with row factory"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def run_modal_cmd(args: list[str]) -> tuple[int, str, str]:
    """Run modal CLI command and return (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            ["modal"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd()
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def get_modal_billing() -> Dict[str, Any]:
    """Get Modal billing summary via CLI"""
    rc, out, err = run_modal_cmd(["billing", "summary"])
    if rc != 0:
        return {"status": "error", "error": err or "modal billing failed"}
    # Parse output - modal billing summary is human-readable text
    # Example: "Metered Cost: 56.42", "Billed Cost: $22.54"
    result = {"raw": out}
    for line in out.strip().split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            val = val.strip().replace('$', '').replace(',', '')
            try:
                out[key] = float(val)
            except:
                out[key] = val.strip()
    return out


def get_modal_apps() -> List[Dict]:
    """List deployed apps via modal CLI"""
    rc, out, err = run_modal_cmd(["app", "list", "--json"])
    if rc != 0:
        return []
    try:
        return json.loads(out)
    except:
        return []


def get_modal_app_costs(app_name: str) -> Dict[str, float]:
    """Get cost breakdown for a specific app (if Modal API supports)"""
    # Modal CLI doesn't expose per-app cost directly via CLI
    # This would need Modal API or billing export
    return {"status": "unavailable", "note": "Per-app cost requires Modal API/billing export"}


def get_modal_secrets_status() -> Dict[str, bool]:
    """Check which required Modal secrets are configured"""
    rc, out, err = run_modal_cmd(["secret", "list", "--json"])
    if rc != 0:
        return {"error": "modal secret list failed", "stderr": err}
    try:
        secrets = json.loads(out)
        required = {
            "hf-token": False,
            "r2-storage-config": False,
            "avireon-secrets": False,
            "avireon-config": False,
            "r2-storage-config": False,
            "agnes-key": False,
        }
        for s in json.loads(out):
            name = s.get("name", "")
            if name in required:
                required[name] = True
    return required


def get_sqlite_conn() -> sqlite3.Connection:
    db_path = Path(__file__).parent.parent / "data" / "beta.db"
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_generation_stats(db_path: str, period: str = "today") -> Dict:
    """Get generation stats from task database"""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    today = datetime.date.today().isoformat()
    month_start = datetime.date.today().replace(day=1).isoformat()

    stats = {}

    # Total generations
    cur = conn.execute("SELECT COUNT(*) FROM ai_tasks WHERE created_at >= date(?)", (today + " 00:00:00",))
    stats["today_total"] = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM ai_tasks WHERE created_at >= date(?)", (month_start,))
    stats["month_total"] = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM ai_tasks WHERE state = 'completed' AND created_at >= date(?)", (today + " 00:00:00",))
    stats["today_completed"] = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM ai_tasks WHERE state = 'completed' AND created_at >= date(?)", (month_start,))
    stats["month_completed"] = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM ai_tasks WHERE state = 'failed' AND created_at >= date(?)", (today + " 00:00:00",))
    stats["today_failed"] = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM ai_tasks WHERE state = 'failed' AND created_at >= date(?)", (month_start,))
    stats["month_failed"] = cur.fetchone()[0] or 0

    # Generation counts from generation_usage
    today_str = datetime.date.today().isoformat()
    month_start_str = datetime.date.today().replace(day=1).isoformat()

    cur.execute("SELECT daily_count FROM generation_usage WHERE user_id = ? AND date = ?", ("total", datetime.date.today().isoformat()))
    row = conn.execute("SELECT SUM(daily_count) FROM generation_usage WHERE date = ?", (today,)).fetchone()
    stats["today_generations"] = row[0] or 0 if row else 0

    cur.execute("SELECT SUM(monthly_count) FROM generation_usage WHERE month_key = ?", (datetime.date.today().strftime("%Y-%m"),))
    stats["month_generations"] = cur.fetchone()[0] or 0

    # Global usage
    cur.execute("SELECT count FROM global_usage WHERE date = ?", (datetime.date.today().isoformat(),))
    row = cur.fetchone()
    stats["global_today"] = row[0] if row else 0

    cur.execute("SELECT SUM(count) FROM global_usage WHERE date >= ?", (month_start,))
    stats["month_global"] = cur.fetchone()[0] or 0

    # Cost logs
    cur.execute("""SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM generation_cost_logs 
                   WHERE created_at >= date(?)""", (datetime.date.today().isoformat(),))
    stats["today_cost"] = cur.fetchone()[0] or 0.0

    cur.execute("SELECT SUM(estimated_cost_usd) FROM generation_cost_logs WHERE created_at >= date(?)", (datetime.date.today().replace(day=1).isoformat(),))
    stats["month_cost"] = cur.fetchone()[0] or 0.0

    # Per-app cost breakdown
    cur.execute("""SELECT provider, SUM(estimated_cost_usd) as cost, COUNT(*) as cnt 
                   FROM generation_cost_logs WHERE created_at >= date(?) 
                   GROUP BY provider""", (datetime.date.today().replace(day=1).isoformat(),))
    stats["provider_costs"] = [dict(r) for r in cur.fetchall()]

    return stats


def get_quota_status() -> Dict:
    """Get quota status from ai_limits"""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cur = conn.cursor()

    today = datetime.date.today().isoformat()
    month_key = datetime.date.today().strftime("%Y-%m")

    cur = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cur = conn.cursor()

    # User-level (sample first user)
    cur.execute("SELECT daily_count, monthly_count FROM generation_usage LIMIT 1")
    row = cur.fetchone()
    daily_used = row[0] if row else 0
    monthly_used = row[1] if row else 0

    # Global
    cur.execute("SELECT count FROM global_usage WHERE date = ?", (datetime.date.today().isoformat(),))
    row = cur.fetchone()
    global_used = row[0] if row else 0

    cur.execute("SELECT SUM(count) FROM global_usage WHERE date >= ?", (datetime.date.today().replace(day=1).isoformat(),))
    row = conn.fetchone()
    monthly_global = row[0] if row else 0

    # Limits from ai_limits
    daily_limit = 1
    monthly_limit = 15
    global_limit = 30

    try:
        from app.services.ai_limits import DAILY_GENERATION_LIMIT, MONTHLY_GENERATION_LIMIT, GLOBAL_DAILY_GENERATION_LIMIT, MODAL_BUDGET_DAILY
        daily_limit = DAILY_GENERATION_LIMIT
        monthly_limit = MONTHLY_GENERATION_LIMIT
        global_limit = GLOBAL_DAILY_GENERATION_LIMIT
        # Step 4: 统一 FAL 预算（兼容旧 MODAL）
        budget_limit = MODAL_BUDGET_DAILY
    except:
        daily_limit = 1
        monthly_limit = 15
        global_limit = 30
        budget_limit = None

    return {
        "daily_used": 1,  # placeholder - need actual user
        "daily_limit": 1,
        "monthly_used": 0,
        "monthly_limit": 15,
        "global_used": 0,
        "global_limit": 30,
        "budget_limit": 10,
        "budget_used": 0,
    }


def build_cost_report(period: str = "today") -> Dict:
    """Build complete cost report"""
    report = {
        "period": "today",
        "generated_at": datetime.datetime.now().isoformat(),
        "total_cost_usd": 0.0,
        "gpu_cost_usd": 0.0,
        "volume_cost_usd": 0.0,
        "r2_cost_usd": 0.0,
        "generation_count": 0,
        "failure_rate": 0.0,
        "budget_usage_pct": 0.0,
        "forecast_monthly_cost": 0.0,
        "alerts": [],
        "recommendations": [],
        "data_availability": {},
    }

    # Modal billing
    modal_billing = get_modal_billing()
    if "error" not in modal_billing:
        # Parse modal billing output
        pass

    # Get generation stats
    stats = get_generation_stats(DB_PATH, "today")

    # Quota status
    quota = get_quota_status()

    # Alerts
    alerts = []
    # Budget checks
    # Step 4: 统一读取 FAL 预算（兼容旧 MODAL）
    _budget_raw = os.getenv("FAL_BUDGET_DAILY") or os.getenv("GPU_BUDGET_DAILY") or os.getenv("MODAL_BUDGET_DAILY")
    if _budget_raw:
        try:
            budget_limit = int(_budget_raw)
        except Exception:
            budget_limit = None
        budget_used = stats.get("today_generations", 0)  # proxy
        if budget_limit and budget_limit > 0:
            pct = (budget_used / budget_limit) * 100
            if pct >= 100:
                alerts.append({"level": "CRITICAL", "code": "BUDGET_EXCEEDED", "message": f"Budget exhausted ({budget_used}/{budget_limit})", "suggestion": "Increase FAL_BUDGET_DAILY or optimize generations"})
            elif pct >= 80:
                alerts.append({"level": "WARNING", "code": "BUDGET_HIGH", "message": f"Budget at {pct:.0f}%", "suggestion": "Monitor closely"})

    # Quota alerts
    if daily_used >= daily_limit * 0.8:
        alerts.append({"level": "WARNING", "code": "DAILY_QUOTA_HIGH", "message": f"Daily quota at {daily_used}/{daily_limit}"})

    # Add data availability notes
    report = {
        "period": "today",
        "total_cost_usd": 0.0,
        "gpu_cost_usd": 0.0,
        "volume_cost_usd": 0.0,
        "r2_cost_usd": 0.0,
        "generation_count": 0,
        "failure_rate": 0.0,
        "budget_usage_pct": 0.0,
        "forecast_monthly_cost": 0.0,
        "alerts": [],
        "recommendations": [],
        "data_availability": {
            "modal_billing": "partial",
            "generation_logs": "available",
            "r2_usage": "unavailable_without_credentials",
        }
    }

    return {}


def generate_cost_report(period: str = "today") -> Dict:
    """Main entry point to generate cost report"""
    return build_cost_report(period)


# FastAPI endpoint (to be registered in main.py or admin router)
def register_cost_advisor_routes(app):
    @app.get("/api/v1/admin/cost-advisor", tags=["admin"])
    async def get_cost_advisor(period: str = "today"):
        """Get cost advisor report"""
        return generate_cost_report(period)


if __name__ == "__main__":
    report = generate_cost_report("today")
    print(json.dumps(report, indent=2, ensure_ascii=False))