"""
FastAPI 主应用

启动方式:
  uvicorn tech_mgmt_ai.api.app:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
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
    logger.info(f"默认 LLM 模型: {settings.DEFAULT_MODEL}")
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
async def run_analysis(
    source: str = Query("mock", description="数据源: mock 或 gitlab"),
    days: int = Query(30, description="分析时间窗口 (天)"),
    enable_llm_review: bool = Query(False, description="是否对 MR/Commit 进行 LLM 代码审查 (会调用大模型, 异步并发)"),
):
    """
    触发一次完整的团队健康分析

    1. 从数据源采集数据 (commits, MRs, pipelines, tasks)
    2. 运行全部数学模型
    3. [可选] 对 MR 和 Commit 抽样进行 LLM 代码审查 (enable_llm_review=true 时, 异步并发)
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
    # 先计算基础模型（不需要 LLM 的部分）

    dora_result = calculate_dora_metrics(merge_requests, pipelines, float(days))

    hero_result = detect_heroes(commits)

    # ---- [可选] LLM 代码审查 (异步并发) ----
    # 必须在计算技术债和团队状态之前进行，因为需要把结果传递给这两个模型
    llm_reviews: list = []
    llm_avg_quality = None
    llm_creating_count = 0

    if enable_llm_review:
        from tech_mgmt_ai.llm.code_reviewer import areview_code_diff
        from tech_mgmt_ai.models.tech_debt import LLMCodeReviewResult

        quality_scores: list[float] = []
        tasks_to_run: list[tuple[str, object, object]] = []  # (kind, obj, coro)

        # --- 1) MR 抽样审查 ---
        if merge_requests:
            mrs_with_diff = [mr for mr in merge_requests if mr.diff and len(mr.diff.strip()) > 100]
            mr_limit = getattr(settings, "TECH_DEBT_LLM_MR_SAMPLE_LIMIT", 5)
            sample_mrs = mrs_with_diff[:mr_limit]

            for mr in sample_mrs:
                coro = areview_code_diff(
                    mr.diff,
                    mr_title=mr.title,
                    author_comment=getattr(mr, "description", "") or "",
                )
                tasks_to_run.append(("mr", mr, coro))

        # --- 2) Commit 抽样审查 ---
        if commits:
            commits_sorted = sorted(
                commits,
                key=lambda c: c.additions + c.deletions,
                reverse=True,
            )
            commits_candidates = [c for c in commits_sorted if (c.additions + c.deletions) > 0]
            sample_limit = getattr(settings, "TECH_DEBT_LLM_COMMIT_SAMPLE_LIMIT", 20)
            sample_commits = commits_candidates[:sample_limit]

            for c in sample_commits:
                pseudo_diff = (
                    f"Commit SHA: {c.sha}\n"
                    f"Author: {c.author}\n"
                    f"CreatedAt: {c.created_at.isoformat()}\n"
                    f"Message:\n{c.message}\n\n"
                    f"Stats: additions={c.additions}, deletions={c.deletions}, files_changed={c.files_changed}\n\n"
                    "说明: 未提供具体代码 diff, 请结合提交信息和变更规模判断该 commit 是否主要在偿还技术债 "
                    "(修复缺陷/重构/清理), 还是在引入新的技术债。"
                )
                coro = areview_code_diff(
                    pseudo_diff,
                    mr_title=f"Commit {c.sha[:8]} by {c.author}",
                    author_comment="",  # message 已包含在 pseudo_diff 的 Message 字段中
                )
                tasks_to_run.append(("commit", c, coro))

        # --- 3) 并发执行所有 LLM 调用 ---
        if tasks_to_run:
            coros = [t[2] for t in tasks_to_run]
            results = await asyncio.gather(*coros, return_exceptions=True)

            for (kind, obj), result in zip([(t[0], t[1]) for t in tasks_to_run], results):
                if isinstance(result, Exception):
                    if kind == "mr":
                        logger.warning("LLM 代码Review 跳过 (MR): mr_id=%s, err=%s", obj.id, result)
                    else:
                        logger.warning("LLM 代码Review 跳过 (Commit): sha=%s, err=%s", obj.sha, result)
                    continue

                if kind == "mr":
                    logger.info(
                        "LLM 代码Review 完成 (MR): mr_id=%s, quality=%d, is_paying_debt=%s, is_creating_debt=%s, summary=%s",
                        obj.id,
                        result.quality_score,
                        result.is_paying_debt,
                        result.is_creating_debt,
                        result.summary[:80] if result.summary else "",
                    )
                    llm_reviews.append(LLMCodeReviewResult(
                        mr_id=obj.id,
                        quality_score=result.quality_score,
                        is_paying_debt=result.is_paying_debt,
                        is_creating_debt=result.is_creating_debt,
                        summary=result.summary,
                    ))
                else:
                    change_size = obj.additions + obj.deletions
                    logger.info(
                        "LLM 代码Review 完成 (Commit 抽样): sha=%s, size=%d, quality=%d, "
                        "is_paying_debt=%s, is_creating_debt=%s, summary=%s",
                        obj.sha,
                        change_size,
                        result.quality_score,
                        result.is_paying_debt,
                        result.is_creating_debt,
                        result.summary[:80] if result.summary else "",
                    )
                    llm_reviews.append(LLMCodeReviewResult(
                        mr_id=0,
                        quality_score=result.quality_score,
                        is_paying_debt=result.is_paying_debt,
                        is_creating_debt=result.is_creating_debt,
                        summary=result.summary,
                    ))

                quality_scores.append(result.quality_score)
                if result.is_creating_debt:
                    llm_creating_count += 1

            if quality_scores:
                llm_avg_quality = sum(quality_scores) / len(quality_scores)
                logger.info(f"LLM 代码质量平均分 (MR + Commit 抽样, 异步并发): {llm_avg_quality:.1f}")

    # ---- 技术债计算 (可选用 LLM 增强) ----
    debt_result = calculate_tech_debt(commits, llm_reviews=llm_reviews if llm_reviews else None)

    # ---- 团队状态计算 (可选用 LLM 增强) ----
    mr_merged = len([mr for mr in merge_requests if mr.state == "merged"])
    llm_total = debt_result.llm_reviewed_mr_count + debt_result.llm_reviewed_commit_count
    state_input = TeamStateInput(
        tasks_created=len([t for t in tasks if t.status == "open"]),
        tasks_closed=len([t for t in tasks if t.status == "done"]),
        total_backlog=len([t for t in tasks if t.status != "done"]),
        debt_tasks=len([t for t in tasks if t.task_type in ("fix", "debt")]),
        feature_tasks=len([t for t in tasks if t.task_type == "feature"]),
        total_tasks=len(tasks),
        reviews_given=sum(mr.comments_count for mr in merge_requests),
        team_size=hero_result.team_size or 1,
        llm_quality_score=llm_avg_quality,
        llm_creating_debt_count=debt_result.llm_creating_debt_count,
        llm_paying_debt_count=debt_result.llm_paying_debt_count,
        llm_total_reviews=llm_total,
        mr_merged_count=mr_merged,
        total_mr_count=len(merge_requests),
    )
    state_result = diagnose_team_state(state_input)

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
                {"author": a, "count": c} for a, c in hero_result.top_debt_contributors
            ]
            if hasattr(hero_result, "top_debt_contributors")
            else [
                {"author": a, "count": c} for a, c in hero_result.top_contributors
            ],
            "debt_top_contributors": [
                {"author": a, "count": c} for a, c in debt_result.top_debt_contributors
            ],
            # 技术债相关详情
            "tech_debt_fix_commit_count": debt_result.fix_commit_count,
            "llm_reviewed_mr_count": debt_result.llm_reviewed_mr_count,
            "llm_reviewed_commit_count": debt_result.llm_reviewed_commit_count,
            "interest_rate_calc_note": debt_result.interest_rate_calc_note,
            # LLM 增强信息
            "llm_enhanced": debt_result.llm_enhanced or state_result.llm_enhanced,
            "llm_paying_debt_count": debt_result.llm_paying_debt_count,
            "llm_creating_debt_count": debt_result.llm_creating_debt_count,
            "code_health_score": state_result.code_health_score,
            # 团队状态可解释性
            "team_state_backlog_score": state_result.backlog_score,
            "team_state_debt_score": state_result.debt_score,
            "team_state_morale_score": state_result.morale_score,
            "team_state_innovation_score": state_result.innovation_score,
            "team_state_creating_debt_score": state_result.creating_debt_score,
            "team_state_calc_explanation": state_result.calc_explanation,
            "team_state_score_ranges": state_result.score_ranges,
            "team_state_description": state_result.description,
        },
    )
    save_snapshot(snapshot)

    # ---- 构建响应 ----
    return AnalyzeResponse(
        health=HealthScoreResponse(
            score=health_result.score,
            level=health_result.level,
            dora_score=health_result.dora_score,
            debt_score=health_result.debt_score,
            hero_score=health_result.hero_score,
            state_score=health_result.state_score,
            dora_contribution=health_result.dora_contribution,
            debt_contribution=health_result.debt_contribution,
            hero_contribution=health_result.hero_contribution,
            state_contribution=health_result.state_contribution,
            w_dora=health_result.w_dora,
            w_debt=health_result.w_debt,
            w_hero=health_result.w_hero,
            w_state=health_result.w_state,
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
            llm_enhanced=debt_result.llm_enhanced,
            llm_paying_debt_count=debt_result.llm_paying_debt_count,
            llm_creating_debt_count=debt_result.llm_creating_debt_count,
            llm_reviewed_mr_count=debt_result.llm_reviewed_mr_count,
            llm_reviewed_commit_count=debt_result.llm_reviewed_commit_count,
            interest_rate_calc_note=debt_result.interest_rate_calc_note,
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
            code_health_score=state_result.code_health_score,
            creating_debt_score=state_result.creating_debt_score,
            description=state_result.description,
            calc_explanation=state_result.calc_explanation,
            score_ranges=state_result.score_ranges,
            llm_enhanced=state_result.llm_enhanced,
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
    # 从存储的原始指标反算各维度归一化分数 (与 health_score 公式一致)
    dora_s = snap.dora_overall_score or 0.5           # 0-1, 越高越好
    debt_s = 1.0 - (snap.tech_debt_interest_rate or 0.5)  # 0-1, 越高越健康
    hero_s = 1.0 - (snap.hero_gini_coefficient or 0.5)    # 0-1, 越低越健康
    state_map = {"falling_behind": 0.0, "treading_water": 0.33, "paying_down_debt": 0.66, "innovating": 1.0}
    state_s = state_map.get(snap.team_state or "", 0.5)
    return AnalyzeResponse(
        health=HealthScoreResponse(
            score=snap.health_score or 0,
            level=snap.health_level or "unknown",
            # 维度原始得分 (0-100)
            dora_score=dora_s * 100,
            debt_score=debt_s * 100,
            hero_score=hero_s * 100,
            state_score=state_s * 100,
            # 维度贡献分 (已乘以权重)
            dora_contribution=settings.HEALTH_W_DORA * dora_s * 100,
            debt_contribution=settings.HEALTH_W_DEBT * debt_s * 100,
            hero_contribution=settings.HEALTH_W_HERO * hero_s * 100,
            state_contribution=settings.HEALTH_W_STATE * state_s * 100,
            # 权重
            w_dora=settings.HEALTH_W_DORA,
            w_debt=settings.HEALTH_W_DEBT,
            w_hero=settings.HEALTH_W_HERO,
            w_state=settings.HEALTH_W_STATE,
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
            # 优先使用详情中保存的真实修复 commit 数; 旧数据没有时再用估算兜底
            fix_commit_count=details.get(
                "tech_debt_fix_commit_count",
                int((snap.tech_debt_interest_rate or 0) * (snap.total_commits or 0)),
            ),
            total_commit_count=snap.total_commits or 0,
            llm_enhanced=details.get("llm_enhanced", False),
            llm_paying_debt_count=details.get("llm_paying_debt_count", 0),
            llm_creating_debt_count=details.get("llm_creating_debt_count", 0),
            llm_reviewed_mr_count=details.get("llm_reviewed_mr_count", 0),
            llm_reviewed_commit_count=details.get("llm_reviewed_commit_count", 0),
            interest_rate_calc_note=details.get("interest_rate_calc_note", ""),
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
            backlog_score=details.get("team_state_backlog_score", 0),
            debt_score=details.get("team_state_debt_score", 0),
            morale_score=details.get("team_state_morale_score", 0),
            innovation_score=details.get("team_state_innovation_score", 0),
            code_health_score=details.get("code_health_score", 0.5),
            creating_debt_score=details.get("team_state_creating_debt_score", 0),
            description=details.get("team_state_description", ""),
            calc_explanation=details.get("team_state_calc_explanation", ""),
            score_ranges=details.get("team_state_score_ranges", ""),
            llm_enhanced=details.get("llm_enhanced", False),
        ),
        report_markdown=snap.report_markdown or "",
        created_at=snap.created_at.isoformat() if snap.created_at else "",
    )
