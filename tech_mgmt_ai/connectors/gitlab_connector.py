"""
GitLab 数据连接器

通过 GitLab REST API v4 采集代码仓库的管理数据:
- Commit 历史 (用于英雄检测、技术债判定)
- Merge Request (用于 Lead Time、代码Review)
- Pipeline (用于部署频率、变更失败率、MTTR)

API 文档: https://docs.gitlab.com/ee/api/
"""

import logging
from datetime import datetime

import httpx

from tech_mgmt_ai.config import settings
from tech_mgmt_ai.connectors import (
    BaseConnector,
    CommitInfo,
    MergeRequestInfo,
    PipelineInfo,
    TaskInfo,
)

logger = logging.getLogger(__name__)


class GitLabConnector(BaseConnector):
    """
    GitLab REST API v4 连接器

    采集代码仓库数据, 作为系统的核心 "传感器" (Sensor)。
    映射《An Elegant Puzzle》2.1节: 通过工程遥测获取 "存量与流量" 数据。
    """

    def __init__(
        self,
        gitlab_url: str | None = None,
        token: str | None = None,
        project_ids: list[int] | None = None,
    ):
        """
        Args:
            gitlab_url: GitLab 实例地址, 默认从 settings 读取
            token: Personal Access Token, 默认从 settings 读取
            project_ids: 要监控的项目 ID 列表, 默认从 settings 读取
        """
        self.gitlab_url = (gitlab_url or settings.GITLAB_URL).rstrip("/")
        self._token = token or (
            settings.GITLAB_TOKEN.get_secret_value() if settings.GITLAB_TOKEN else ""
        )
        self.project_ids = project_ids or settings.gitlab_project_id_list
        self._api_base = f"{self.gitlab_url}/api/v4"
        self._headers = {"PRIVATE-TOKEN": self._token}

    def _get(self, path: str, params: dict | None = None) -> list[dict]:
        """
        带自动分页的 GitLab API GET 请求

        GitLab API 默认每页 20 条, 此方法自动遍历所有页面。
        """
        results: list[dict] = []
        page = 1
        per_page = 100  # 最大每页条数

        while True:
            p = {"page": page, "per_page": per_page}
            if params:
                p.update(params)

            try:
                resp = httpx.get(
                    f"{self._api_base}{path}",
                    headers=self._headers,
                    params=p,
                    timeout=30.0,
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.error(f"GitLab API 请求失败: {path} → {e}")
                break

            data = resp.json()
            if not isinstance(data, list):
                # 某些接口返回单个对象
                results.append(data)
                break

            results.extend(data)
            if len(data) < per_page:
                break
            page += 1

        return results

    @staticmethod
    def _parse_datetime(dt_str: str | None) -> datetime | None:
        """解析 GitLab API 的 ISO 8601 时间字符串"""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def fetch_commits(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[CommitInfo]:
        """
        从配置的所有 GitLab 项目中获取 Commit 历史

        每条 Commit 包含: 作者、提交消息、变更行数等信息。
        这些数据将用于:
        - 英雄检测模型: 计算提交集中度 (基尼系数)
        - 技术债模型: 通过 commit message 关键词识别修复类提交
        """
        all_commits: list[CommitInfo] = []

        for pid in self.project_ids:
            params: dict = {"with_stats": True}
            if since:
                params["since"] = since.isoformat()
            if until:
                params["until"] = until.isoformat()

            raw_commits = self._get(f"/projects/{pid}/repository/commits", params)

            alias_map = settings.author_alias_map
            for c in raw_commits:
                # 获取单个 commit 的详细统计 (行级变更数, 需 with_stats=true)
                stats = c.get("stats", {})
                raw_author = c.get("author_name", "unknown")
                author = alias_map.get(raw_author, raw_author) if alias_map else raw_author
                all_commits.append(CommitInfo(
                    sha=c.get("id", ""),
                    author=author,
                    message=c.get("message", ""),
                    created_at=self._parse_datetime(c.get("created_at")) or datetime.now(),
                    additions=stats.get("additions", 0),
                    deletions=stats.get("deletions", 0),
                    files_changed=stats.get("total", 0),
                ))

        logger.info(
            f"GitLab: 获取 {len(all_commits)} 条 Commits "
            f"(来自 {len(self.project_ids)} 个项目)"
        )
        return all_commits

    def fetch_merge_requests(
        self,
        state: str = "all",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[MergeRequestInfo]:
        """
        从 GitLab 获取 Merge Request 列表

        MR 数据用于:
        - DORA Lead Time: 从首次提交到合并的时间
        - 代码Review: 通过 LLM 分析 Diff 给出质量评估
        - 团队状态: Review 参与度作为士气代理指标
        """
        all_mrs: list[MergeRequestInfo] = []

        for pid in self.project_ids:
            params: dict = {"state": state}
            if since:
                params["created_after"] = since.isoformat()
            if until:
                params["created_before"] = until.isoformat()

            raw_mrs = self._get(f"/projects/{pid}/merge_requests", params)

            for mr in raw_mrs:
                # 获取 MR 的 diff (用于 LLM 代码Review)
                diff_text = ""
                mr_iid = mr.get("iid")
                if mr_iid:
                    try:
                        changes_resp = httpx.get(
                            f"{self._api_base}/projects/{pid}/merge_requests/{mr_iid}/changes",
                            headers=self._headers,
                            timeout=30.0,
                        )
                        if changes_resp.status_code == 200:
                            changes = changes_resp.json().get("changes", [])
                            diff_parts = []
                            for ch in changes:
                                diff_parts.append(
                                    f"--- {ch.get('old_path', '')}\n"
                                    f"+++ {ch.get('new_path', '')}\n"
                                    f"{ch.get('diff', '')}"
                                )
                            diff_text = "\n".join(diff_parts)
                    except httpx.HTTPError:
                        logger.warning(f"获取 MR #{mr_iid} Diff 失败")

                # 提取 Reviewer 列表
                reviewers = [
                    r.get("username", "")
                    for r in mr.get("reviewers", [])
                    if r.get("username")
                ]

                all_mrs.append(MergeRequestInfo(
                    id=mr.get("id", 0),
                    title=mr.get("title", ""),
                    author=mr.get("author", {}).get("username", "unknown"),
                    state=mr.get("state", ""),
                    created_at=self._parse_datetime(mr.get("created_at")) or datetime.now(),
                    merged_at=self._parse_datetime(mr.get("merged_at")),
                    diff=diff_text,
                    reviewers=reviewers,
                    comments_count=mr.get("user_notes_count", 0),
                ))

        logger.info(f"GitLab: 获取 {len(all_mrs)} 条 Merge Requests")
        return all_mrs

    def fetch_pipelines(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[PipelineInfo]:
        """
        从 GitLab 获取 CI/CD Pipeline 列表

        Pipeline 数据用于:
        - DORA Deployment Frequency: 部署频率
        - DORA Change Failure Rate: 变更失败率
        - DORA MTTR: 失败后恢复时间
        """
        all_pipelines: list[PipelineInfo] = []

        for pid in self.project_ids:
            params: dict = {}
            if since:
                params["updated_after"] = since.isoformat()
            if until:
                params["updated_before"] = until.isoformat()

            raw_pipelines = self._get(f"/projects/{pid}/pipelines", params)

            for p in raw_pipelines:
                created = self._parse_datetime(p.get("created_at"))
                finished = self._parse_datetime(p.get("updated_at"))
                duration = 0.0
                if created and finished:
                    duration = (finished - created).total_seconds()

                # 判断是否为部署类 Pipeline
                # 常见策略: 通过 ref 名称 (main/master/release) 或 source (deploy)
                ref = p.get("ref", "")
                source = p.get("source", "")
                is_deploy = (
                    ref in ("main", "master", "production")
                    or "release" in ref
                    or source == "deploy"
                )

                all_pipelines.append(PipelineInfo(
                    id=p.get("id", 0),
                    status=p.get("status", ""),
                    created_at=created or datetime.now(),
                    finished_at=finished,
                    duration_seconds=duration,
                    is_deployment=is_deploy,
                ))

        logger.info(f"GitLab: 获取 {len(all_pipelines)} 条 Pipelines")
        return all_pipelines

    def fetch_tasks(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[TaskInfo]:
        """
        从 GitLab Issues 获取任务数据 (作为项目管理数据的补充)

        注: 主要的任务数据应来自飞书或 Jira, GitLab Issues 作为补充源。
        """
        all_tasks: list[TaskInfo] = []

        for pid in self.project_ids:
            params: dict = {}
            if since:
                params["created_after"] = since.isoformat()
            if until:
                params["created_before"] = until.isoformat()

            raw_issues = self._get(f"/projects/{pid}/issues", params)

            for issue in raw_issues:
                # 通过 Label 推断任务类型
                labels = [lbl.lower() for lbl in issue.get("labels", [])]
                task_type = "feature"
                if any(l in labels for l in ("bug", "fix", "hotfix")):
                    task_type = "fix"
                elif any(l in labels for l in ("tech-debt", "refactor", "chore")):
                    task_type = "debt"
                elif any(l in labels for l in ("ops", "infra", "devops")):
                    task_type = "ops"

                all_tasks.append(TaskInfo(
                    id=str(issue.get("iid", "")),
                    title=issue.get("title", ""),
                    description=issue.get("description", ""),
                    status="done" if issue.get("state") == "closed" else "open",
                    task_type=task_type,
                    assignee=(issue.get("assignee") or {}).get("username", ""),
                    created_at=self._parse_datetime(issue.get("created_at")),
                    due_date=self._parse_datetime(issue.get("due_date")),
                    completed_at=self._parse_datetime(issue.get("closed_at")),
                ))

        logger.info(f"GitLab: 获取 {len(all_tasks)} 条 Issues/Tasks")
        return all_tasks
