"""
CLI 入口 — 技术管理分析命令行工具

使用方法:
  python -m tech_mgmt_ai analyze              # 运行完整分析 (使用 Mock 数据)
  python -m tech_mgmt_ai analyze --source gitlab  # 使用 GitLab 数据
  python -m tech_mgmt_ai team-sizing --engineers 24 --managers 3
"""

import json
import logging
import sys
from datetime import datetime, timedelta

import click

from tech_mgmt_ai.config import settings


def _setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.group()
@click.version_option(version="0.1.0", prog_name="tech-mgmt-ai")
def main():
    """
    AI 技术管理工具 — 基于《An Elegant Puzzle》

    为中高层技术管理者提供数据驱动的管理决策支持。
    """
    _setup_logging()


@main.command()
@click.option(
    "--source", type=click.Choice(["mock", "gitlab"]), default="mock",
    help="数据源: mock (模拟数据) 或 gitlab (真实 GitLab 数据)"
)
@click.option("--days", type=int, default=30, help="分析时间窗口 (天)")
@click.option("--notify/--no-notify", default=False, help="是否发送告警通知")
def analyze(source: str, days: int, notify: bool):
    """运行完整的团队健康分析"""
    click.echo("=" * 60)
    click.echo("  AI 技术管理工具 — 团队健康分析")
    click.echo("  基于《An Elegant Puzzle》(工程管理的要素)")
    click.echo("=" * 60)
    click.echo()

    since = datetime.now() - timedelta(days=days)
    until = datetime.now()

    if source == "gitlab":
        click.echo(f"📡 数据源: GitLab ({settings.GITLAB_URL})")
        click.echo(f"📅 分析窗口: 最近 {days} 天\n")

        from tech_mgmt_ai.connectors.gitlab_connector import GitLabConnector
        connector = GitLabConnector()
        commits = connector.fetch_commits(since=since, until=until)
        merge_requests = connector.fetch_merge_requests(state="all", since=since, until=until)
        pipelines = connector.fetch_pipelines(since=since, until=until)
        tasks = connector.fetch_tasks(since=since, until=until)
    else:
        click.echo("📡 数据源: Mock 模拟数据")
        click.echo(f"📅 分析窗口: 最近 {days} 天\n")
        commits, merge_requests, pipelines, tasks = _generate_mock_data(since, until)

    # === 1. 技术债分析 ===
    from tech_mgmt_ai.models.tech_debt import calculate_tech_debt
    debt_result = calculate_tech_debt(commits)
    click.echo(debt_result.description)
    click.echo()

    # === 2. DORA 指标 ===
    from tech_mgmt_ai.models.dora_metrics import calculate_dora_metrics
    dora_result = calculate_dora_metrics(merge_requests, pipelines, float(days))
    click.echo(dora_result.description)
    click.echo()

    # === 3. 英雄检测 ===
    from tech_mgmt_ai.models.hero_detector import detect_heroes
    hero_result = detect_heroes(commits)
    click.echo(hero_result.description)
    click.echo()

    # === 4. 团队状态诊断 ===
    from tech_mgmt_ai.models.team_state import TeamStateInput, diagnose_team_state
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
    click.echo(state_result.description)
    click.echo()

    # === 5. 综合健康分 ===
    from tech_mgmt_ai.metrics.health_score import calculate_health_score
    health = calculate_health_score(
        dora=dora_result,
        tech_debt=debt_result,
        hero=hero_result,
        team_state=state_result,
    )
    click.echo(health.description)
    click.echo()

    # === 发送告警 ===
    if notify and health.level in ("attention", "danger"):
        from tech_mgmt_ai.alerts.notifiers import send_alert
        alert_content = (
            f"{health.description}\n\n"
            f"---\n\n"
            f"{debt_result.description}\n\n"
            f"{hero_result.description}"
        )
        send_alert(
            title=f"团队健康分 {health.score:.0f}/100 [{health.level}]",
            content=alert_content,
        )

    click.echo("=" * 60)
    click.echo("  分析完成")
    click.echo("=" * 60)


@main.command()
@click.option("--engineers", type=int, required=True, help="工程师人数")
@click.option("--managers", type=int, required=True, help="经理人数")
@click.option("--directors", type=int, default=0, help="高级经理/总监人数")
@click.option("--oncall", type=int, default=0, help="值班轮值池人数")
def team_sizing(engineers: int, managers: int, directors: int, oncall: int):
    """团队规模校准检查 (基于书 1.1节的4个原则)"""
    from tech_mgmt_ai.models.team_sizing import check_team_sizing

    result = check_team_sizing(
        engineers=engineers,
        managers=managers,
        directors=directors,
        oncall_pool_size=oncall,
    )
    click.echo(result.description)


def _generate_mock_data(since, until):
    """生成模拟数据用于演示"""
    from tech_mgmt_ai.connectors import CommitInfo, MergeRequestInfo, PipelineInfo, TaskInfo

    # 模拟 8 人团队, 30 天数据
    authors = ["alice", "bob", "charlie", "diana", "eve", "frank", "grace", "henry"]
    commits = []
    for i in range(120):
        # 模拟不均匀分布: alice 和 bob 提交较多 (用于测试英雄检测)
        idx = 0 if i % 3 == 0 else (1 if i % 5 == 0 else i % len(authors))
        is_fix = i % 7 == 0  # 约 14% 是修复
        commits.append(CommitInfo(
            sha=f"abc{i:04d}",
            author=authors[idx],
            message=f"{'fix: 修复问题 #' + str(i) if is_fix else 'feat: 实现功能 #' + str(i)}",
            created_at=since + timedelta(hours=i * 6),
            additions=50 + i * 2,
            deletions=20 + i,
            files_changed=3,
        ))

    # 模拟 diff 片段 (长度 >100 以便触发 LLM 审查)
    _fake_diff = (
        "diff --git a/src/module.py b/src/module.py\n"
        "--- a/src/module.py\n+++ b/src/module.py\n"
        "@@ -1,5 +1,8 @@\n def handler():\n     pass\n+# 新增逻辑\n+    result = process()\n+    return result\n"
    )
    merge_requests = []
    for i in range(25):
        merged = i % 4 != 0  # 75% 已合并
        created = since + timedelta(days=i)
        # 部分 MR 标题模拟偿债/引入债/新功能, 便于 LLM 判定
        if i % 5 == 0:
            title = f"MR #{i+1}: fix 修复 #{(i//5)+1}"
        elif i % 5 == 1:
            title = f"MR #{i+1}: refactor 重构"
        elif i % 5 == 2:
            title = f"MR #{i+1}: 临时方案 绕过校验"  # 可能被 LLM 判为引入技术债
        else:
            title = f"MR #{i+1}: 功能实现"
        merge_requests.append(MergeRequestInfo(
            id=i + 1,
            title=title,
            author=authors[i % len(authors)],
            state="merged" if merged else "opened",
            created_at=created,
            merged_at=created + timedelta(hours=36) if merged else None,
            diff=_fake_diff,  # 供 LLM 审查使用
            reviewers=[authors[(i+1) % len(authors)]],
            comments_count=2 + i % 3,
        ))

    pipelines = []
    for i in range(40):
        is_deploy = i % 3 == 0
        is_failed = i % 10 == 0
        created = since + timedelta(hours=i * 18)
        pipelines.append(PipelineInfo(
            id=i + 1,
            status="failed" if is_failed else "success",
            created_at=created,
            finished_at=created + timedelta(minutes=15),
            duration_seconds=900,
            is_deployment=is_deploy,
        ))

    tasks = []
    for i in range(50):
        types = ["feature", "feature", "feature", "fix", "debt", "ops"]
        statuses = ["done", "done", "done", "open", "open"]
        tasks.append(TaskInfo(
            id=str(i + 1),
            title=f"Task #{i+1}",
            status=statuses[i % len(statuses)],
            task_type=types[i % len(types)],
            created_at=since + timedelta(days=i % 30),
        ))

    return commits, merge_requests, pipelines, tasks


if __name__ == "__main__":
    main()
