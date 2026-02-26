"""
FastAPI 主应用

启动方式:
  uvicorn tech_mgmt_ai.api.app:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from tech_mgmt_ai.api.schemas import (
    AnalyzeResponse,
    DORAMetricsResponse,
    HealthScoreResponse,
    HeroResponse,
    HistoryPointResponse,
    TeamSizingRequest,
    TeamSizingIssueResponse,
    TeamSizingResponse,
    TeamStateResponse,
    TechDebtResponse,
)
from tech_mgmt_ai.storage.database import init_db
from tech_mgmt_ai.storage.models import MetricsSnapshot
from tech_mgmt_ai.storage.metrics_store import save_snapshot, get_latest_snapshot, get_history as query_history
from tech_mgmt_ai.models.tech_debt import calculate_tech_debt
from tech_mgmt_ai.models.dora_metrics import calculate_dora_metrics
from tech_mgmt_ai.models.hero_detector import detect_heroes
from tech_mgmt_ai.models.team_state import TeamStateInput, diagnose_team_state
from tech_mgmt_ai.models.team_sizing import check_team_sizing
from tech_mgmt_ai.metrics.health_score import calculate_health_score
from tech_mgmt_ai.config import settings
from tech_mgmt_ai.connectors.gitlab_connector import GitLabConnector
from tech_mgmt_ai.__main__ import _generate_mock_data

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动时初始化数据库"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    init_db()
    logger.info("tech_mgmt_ai API 启动完成")
    yield
    logger.info("tech_mgmt_ai API 关闭")


app = FastAPI(
    title="AI 技术管理工具",
    description="基于《An Elegant Puzzle》为中高层技术管理者提供数据驱动的管理决策支持",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API 路由
# ============================================================================

@app.get("/api/health")
def health_check():
    """服务健康检查"""
    return {"status": "ok", "service": "tech_mgmt_ai", "version": "0.1.0"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def run_analysis(
    source: str = Query("mock", description="数据源: mock 或 gitlab"),
    days: int = Query(30, description="分析时间窗口 (天)"),
    enable_llm_review: bool = Query(False, description="是否对 MR 进行 LLM 代码审查 (会调用大模型, 产生日志)"),
):
    """
    触发一次完整的团队健康分析

    1. 从数据源采集数据 (commits, MRs, pipelines, tasks)
    2. 运行全部数学模型
    3. [可选] 对 MR 进行 LLM 代码审查 (enable_llm_review=true 时)
    4. 计算综合健康分
    5. 保存快照到数据库
    6. 返回完整结果
    """
    since = datetime.now() - timedelta(days=days)
    until = datetime.now()

    # ---- 数据采集 ----
    if source == "gitlab":
        connector = GitLabConnector()
        commits = connector.fetch_commits(since=since, until=until)
        merge_requests = connector.fetch_merge_requests(state="all", since=since, until=until)
        pipelines = connector.fetch_pipelines(since=since, until=until)
        tasks = connector.fetch_tasks(since=since, until=until)
    else:
        # 使用 CLI 中的 mock 数据生成器
        commits, merge_requests, pipelines, tasks = _generate_mock_data(since, until)

    # ---- 模型计算 ----
    debt_result = calculate_tech_debt(commits)

    dora_result = calculate_dora_metrics(merge_requests, pipelines, float(days))

    hero_result = detect_heroes(commits)

    state_input = TeamStateInput(
        tasks_created=len([t for t in tasks if t.status == "open"]),
        tasks_closed=len([t for t in tasks if t.status == "done"]),
        total_backlog=len([t for t in tasks if t.status != "done"]),
        debt_tasks=len([t for t in tasks if t.task_type in ("fix", "debt")]),
        feature_tasks=len([t for t in tasks if t.task_type == "feature"]),
        total_tasks=len(tasks),
        reviews_given=sum(mr.comments_count for mr in merge_requests),
        team_size=hero_result.team_size or 1,
    )
    state_result = diagnose_team_state(state_input)

    # ---- [可选] LLM 代码审查 (仅抽样 1-2 个 MR, 用于验证 LLM 调用并产生日志) ----
    if enable_llm_review and merge_requests:
        from tech_mgmt_ai.llm.code_reviewer import review_code_diff

        mrs_with_diff = [mr for mr in merge_requests if mr.diff and len(mr.diff.strip()) > 100]
        sample_mrs = mrs_with_diff[:2]  # 最多审查 2 个 MR
        for mr in sample_mrs:
            try:
                result = review_code_diff(mr.diff, mr_title=mr.title)
                logger.info(
                    "LLM 代码Review 完成: mr_id=%s, quality=%d, is_paying_debt=%s, summary=%s",
                    mr.id, result.quality_score, result.is_paying_debt, result.summary[:80] if result.summary else "",
                )
            except Exception as e:
                logger.warning("LLM 代码Review 跳过 (可能未配置 LLM): mr_id=%s, err=%s", mr.id, e)
        if not sample_mrs:
            logger.info("LLM 代码Review: 无有效 Diff 的 MR, 跳过")

    health_result = calculate_health_score(
        dora=dora_result,
        tech_debt=debt_result,
        hero=hero_result,
        team_state=state_result,
    )

    # ---- 生成报告 ----
    report = "\n\n".join([
        health_result.description,
        dora_result.description,
        debt_result.description,
        hero_result.description,
        state_result.description,
    ])

    # ---- 持久化 ----
    snapshot = MetricsSnapshot(
        created_at=datetime.now(),
        health_score=health_result.score,
        health_level=health_result.level,
        dora_lead_time_hours=dora_result.lead_time_hours,
        dora_deploy_frequency=dora_result.deploy_frequency,
        dora_change_failure_rate=dora_result.change_failure_rate,
        dora_mttr_hours=dora_result.mttr_hours,
        dora_overall_score=dora_result.overall_score,
        dora_overall_level=dora_result.overall_level.name.lower() if hasattr(dora_result.overall_level, 'name') else str(dora_result.overall_level),
        tech_debt_interest_rate=debt_result.interest_rate,
        tech_debt_level=debt_result.level,
        tech_debt_stock=debt_result.debt_stock,
        hero_gini_coefficient=hero_result.gini_coefficient,
        hero_level=hero_result.level,
        hero_team_size=hero_result.team_size,
        team_state=state_result.state.value,
        team_state_score=state_result.score,
        total_commits=len(commits),
        total_merge_requests=len(merge_requests),
        total_pipelines=len(pipelines),
        total_tasks=len(tasks),
        report_markdown=report,
        details_json={
            "hero_top_contributors": [
                {"author": a, "count": c} for a, c in hero_result.top_contributors
            ],
            "debt_top_contributors": [
                {"author": a, "count": c} for a, c in debt_result.top_debt_contributors
            ],
        },
    )
    save_snapshot(snapshot)

    # ---- 构建响应 ----
    return AnalyzeResponse(
        health=HealthScoreResponse(
            score=health_result.score,
            level=health_result.level,
            dora_contribution=health_result.dora_contribution,
            debt_contribution=health_result.debt_contribution,
            hero_contribution=health_result.hero_contribution,
            state_contribution=health_result.state_contribution,
        ),
        dora=DORAMetricsResponse(
            lead_time_hours=dora_result.lead_time_hours,
            deploy_frequency=dora_result.deploy_frequency,
            change_failure_rate=dora_result.change_failure_rate,
            mttr_hours=dora_result.mttr_hours,
            overall_score=dora_result.overall_score,
            overall_level=dora_result.overall_level.name.lower() if hasattr(dora_result.overall_level, 'name') else str(dora_result.overall_level),
        ),
        tech_debt=TechDebtResponse(
            interest_rate=debt_result.interest_rate,
            level=debt_result.level,
            stock=debt_result.debt_stock,
            fix_commit_count=debt_result.fix_commit_count,
            total_commit_count=debt_result.total_commit_count,
        ),
        hero=HeroResponse(
            gini_coefficient=hero_result.gini_coefficient,
            level=hero_result.level,
            team_size=hero_result.team_size,
            top_contributors=[
                {"author": a, "count": c} for a, c in hero_result.top_contributors
            ],
        ),
        team_state=TeamStateResponse(
            state=state_result.state.value,
            score=state_result.score,
            backlog_score=state_result.backlog_score,
            debt_score=state_result.debt_score,
            morale_score=state_result.morale_score,
            innovation_score=state_result.innovation_score,
            description=state_result.description,
        ),
        report_markdown=report,
        created_at=datetime.now().isoformat(),
    )


@app.get("/api/metrics/latest", response_model=AnalyzeResponse | None)
def get_latest():
    """获取最近一次分析结果"""
    snap = get_latest_snapshot()
    if not snap:
        return None

    return _snapshot_to_response(snap)


@app.get("/api/metrics/history", response_model=list[HistoryPointResponse])
def get_history(
    days: int = Query(90, description="查询最近多少天的历史"),
):
    """获取历史指标数据 (用于趋势图)"""
    since = datetime.now() - timedelta(days=days)
    snapshots = query_history(since=since)

    return [
        HistoryPointResponse(
            created_at=s.created_at.isoformat() if s.created_at else "",
            health_score=s.health_score or 0,
            dora_overall_score=s.dora_overall_score or 0,
            tech_debt_interest_rate=s.tech_debt_interest_rate or 0,
            hero_gini_coefficient=s.hero_gini_coefficient or 0,
            team_state=s.team_state or "unknown",
        )
        for s in snapshots
    ]


@app.post("/api/team-sizing", response_model=TeamSizingResponse)
def check_sizing(req: TeamSizingRequest):
    """团队规模校准"""
    result = check_team_sizing(
        engineers=req.engineers,
        managers=req.managers,
        directors=req.directors,
        oncall_pool_size=req.oncall_pool_size,
    )
    return TeamSizingResponse(
        is_healthy=result.is_healthy,
        issues=[
            TeamSizingIssueResponse(
                rule=i.rule,
                severity=i.severity,
                current_value=i.current_value,
                expected_range=i.expected_range,
                suggestion=i.suggestion,
            )
            for i in result.issues
        ],
        description=result.description,
    )


def _snapshot_to_response(snap: MetricsSnapshot) -> AnalyzeResponse:
    """将数据库快照转换为 API 响应, 从存储的指标反算各维度贡献分"""
    details = snap.details_json or {}
    # 从存储的原始指标反算各维度贡献 (与 health_score 公式一致)
    dora_s = snap.dora_overall_score or 0.5
    debt_s = 1.0 - (snap.tech_debt_interest_rate or 0.5)
    hero_s = 1.0 - (snap.hero_gini_coefficient or 0.5)
    state_map = {"falling_behind": 0.0, "treading_water": 0.33, "paying_down_debt": 0.66, "innovating": 1.0}
    state_s = state_map.get(snap.team_state or "", 0.5)
    return AnalyzeResponse(
        health=HealthScoreResponse(
            score=snap.health_score or 0,
            level=snap.health_level or "unknown",
            dora_contribution=settings.HEALTH_W_DORA * dora_s * 100,
            debt_contribution=settings.HEALTH_W_DEBT * debt_s * 100,
            hero_contribution=settings.HEALTH_W_HERO * hero_s * 100,
            state_contribution=settings.HEALTH_W_STATE * state_s * 100,
        ),
        dora=DORAMetricsResponse(
            lead_time_hours=snap.dora_lead_time_hours or 0,
            deploy_frequency=snap.dora_deploy_frequency or 0,
            change_failure_rate=snap.dora_change_failure_rate or 0,
            mttr_hours=snap.dora_mttr_hours or 0,
            overall_score=snap.dora_overall_score or 0,
            overall_level=snap.dora_overall_level or "low",
        ),
        tech_debt=TechDebtResponse(
            interest_rate=snap.tech_debt_interest_rate or 0,
            level=snap.tech_debt_level or "healthy",
            stock=snap.tech_debt_stock or 0,
            fix_commit_count=int((snap.tech_debt_interest_rate or 0) * (snap.total_commits or 0)),
            total_commit_count=snap.total_commits or 0,
        ),
        hero=HeroResponse(
            gini_coefficient=snap.hero_gini_coefficient or 0,
            level=snap.hero_level or "healthy",
            team_size=snap.hero_team_size or 0,
            top_contributors=details.get("hero_top_contributors", []),
        ),
        team_state=TeamStateResponse(
            state=snap.team_state or "unknown",
            score=snap.team_state_score or 0,
        ),
        report_markdown=snap.report_markdown or "",
        created_at=snap.created_at.isoformat() if snap.created_at else "",
    )
