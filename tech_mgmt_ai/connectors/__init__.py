"""
数据连接器抽象基类

定义所有外部数据源连接器的标准接口。
具体实现 (GitLab, 飞书等) 通过继承此基类并实现抽象方法来提供数据。

设计理念: 映射《An Elegant Puzzle》2.1节 "系统思维" 中的 "存量与流量" 概念,
每个连接器就是系统的 "传感器", 负责采集流量数据 (commits, MRs, tasks)
和存量数据 (积压任务数, 团队人数)。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


# ============================================================================
# 标准化数据结构 — 跨连接器通用
# ============================================================================

@dataclass
class CommitInfo:
    """代码提交信息"""
    sha: str                       # 提交哈希
    author: str                    # 作者
    message: str                   # 提交消息
    created_at: datetime           # 提交时间
    additions: int = 0             # 新增行数
    deletions: int = 0             # 删除行数
    files_changed: int = 0         # 变更文件数
    project_id: int = 0            # 项目 ID（用于按项目统计）


@dataclass
class MergeRequestInfo:
    """合并请求信息"""
    id: int                        # MR ID
    title: str                     # 标题
    author: str                    # 作者
    state: str                     # 状态: opened, merged, closed
    created_at: datetime           # 创建时间
    merged_at: datetime | None     # 合并时间 (未合并时为 None)
    diff: str = ""                 # Diff 内容 (用于 LLM 代码Review)
    description: str = ""          # 作者说明/描述 (与 diff 一并推给 LLM)
    reviewers: list[str] = field(default_factory=list)  # 参与Review的人
    comments_count: int = 0        # 评论数


@dataclass
class PipelineInfo:
    """CI/CD Pipeline 信息"""
    id: int                        # Pipeline ID
    status: str                    # 状态: success, failed, canceled
    created_at: datetime           # 创建时间
    finished_at: datetime | None   # 结束时间
    duration_seconds: float = 0    # 总耗时 (秒)
    is_deployment: bool = False    # 是否为部署类 Pipeline


@dataclass
class TaskInfo:
    """项目管理任务/需求信息"""
    id: str                        # 任务唯一标识
    title: str                     # 任务标题
    description: str = ""          # 任务描述
    status: str = "open"           # 状态: open, in_progress, done, overdue
    task_type: str = "feature"     # 类型: feature, fix, debt, ops
    assignee: str = ""             # 负责人
    created_at: datetime | None = None   # 创建时间
    due_date: datetime | None = None      # 截止日期
    completed_at: datetime | None = None  # 完成时间
    priority: str = "medium"       # 优先级: critical, high, medium, low


# ============================================================================
# 连接器抽象基类
# ============================================================================

class BaseConnector(ABC):
    """
    数据连接器抽象基类

    所有外部数据源必须实现这些方法, 以确保逻辑层 (models/) 可以
    透明地消费来自不同源的数据。
    """

    @abstractmethod
    def fetch_commits(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[CommitInfo]:
        """
        获取代码提交历史

        Args:
            since: 起始时间 (含), None 表示不限制
            until: 结束时间 (含), None 表示不限制

        Returns:
            提交信息列表, 按时间正序排列
        """
        ...

    @abstractmethod
    def fetch_merge_requests(
        self,
        state: str = "all",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[MergeRequestInfo]:
        """
        获取合并请求列表

        Args:
            state: 筛选状态 ("all", "opened", "merged", "closed")
            since: 起始时间
            until: 结束时间

        Returns:
            合并请求信息列表
        """
        ...

    @abstractmethod
    def fetch_pipelines(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[PipelineInfo]:
        """
        获取 CI/CD Pipeline 列表

        Args:
            since: 起始时间
            until: 结束时间

        Returns:
            Pipeline 信息列表
        """
        ...

    @abstractmethod
    def fetch_tasks(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[TaskInfo]:
        """
        获取项目管理任务列表

        Args:
            since: 起始时间
            until: 结束时间

        Returns:
            任务信息列表
        """
        ...
