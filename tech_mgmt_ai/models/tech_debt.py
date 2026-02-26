"""
技术债利息率模型

═══════════════════════════════════════════════════════════════════════════════
理论依据: 《An Elegant Puzzle》2.5节 & 2.6节
  - 2.5节: "用指标指导广泛的组织变革" — 建立基线指标来衡量技术债
  - 2.6节: "迁移, 解决技术债务的唯一可扩展方法"
  - 4.6节: 技术债像 "沙尘暴", 多年系统滥用后逐渐成型

参考文献:
  - 《系统之美》(Thinking in Systems) — 存量/流量模型
  - 《凤凰项目》(The Phoenix Project) — 技术债的累积效应
═══════════════════════════════════════════════════════════════════════════════

核心公式:

  利息率 (Interest Rate):
    I = fix_changes / total_changes

  其中:
    fix_changes   = 被判定为 "修复类" 的 Commit 的代码变更量 (additions + deletions)
    total_changes = 所有 Commit 的代码变更量

  含义: I 代表团队为维护旧系统 (还利息) 付出的精力占比
    I < 0.15  → 健康, 大部分精力在创造新价值
    I ∈ [0.15, 0.30) → 需关注, 债务开始侵蚀产能
    I ∈ [0.30, 0.50) → 告警, 应启动集中偿债计划
    I ≥ 0.50  → 危险, 债务已严重影响交付能力

  技术债存量 (Stocks & Flows, 基于系统动力学):
    Debt_stock(t) = Debt_stock(t-1) + new_debt_flow - repay_flow

  其中:
    new_debt_flow  = 新增债务 (低质量 commit、缺乏测试等)
    repay_flow     = 偿还债务 (重构、修复、迁移)
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass, field

from tech_mgmt_ai.config import settings
from tech_mgmt_ai.connectors import CommitInfo

logger = logging.getLogger(__name__)


@dataclass
class TechDebtResult:
    """
    技术债分析结果

    Attributes:
        interest_rate: 利息率 (0.0-1.0), 修复类变更占总变更的比例
        level: 债务等级 (healthy / warning / alert / danger)
        total_changes: 总代码变更行数 (additions + deletions)
        fix_changes: 修复类代码变更行数
        fix_commit_count: 被判定为修复类的 Commit 数量
        total_commit_count: 总 Commit 数量
        debt_stock: 技术债存量 (累积值, 正值表示净债务)
        top_debt_contributors: 修复类 Commit 最多的作者 (用于辅助管理决策)
        description: 可读的分析描述
    """
    interest_rate: float = 0.0
    level: str = "healthy"
    total_changes: int = 0
    fix_changes: int = 0
    fix_commit_count: int = 0
    total_commit_count: int = 0
    debt_stock: float = 0.0
    top_debt_contributors: list[tuple[str, int]] = field(default_factory=list)
    description: str = ""


def is_fix_commit(commit: CommitInfo) -> bool:
    """
    判断一条 Commit 是否为 "修复类"

    判定逻辑:
      1. 优先检查 commit message 中是否包含修复关键词 (来自 settings)
      2. 关键词匹配不区分大小写, 检查 message 的前 200 个字符

    关键词列表可通过 TECH_DEBT_FIX_KEYWORDS 环境变量自定义。
    默认: fix, bugfix, hotfix, patch, repair, resolve

    注: 更高级的方案是通过 LLM 进行语义分析 (参见 task_classifier),
    但关键词匹配作为基线方法具有零延迟、零成本的优势。

    Args:
        commit: 代码提交信息

    Returns:
        True 如果该 commit 被判定为修复类
    """
    msg_lower = commit.message[:200].lower()
    keywords = settings.tech_debt_fix_keyword_list
    return any(kw in msg_lower for kw in keywords)


def calculate_tech_debt(
    commits: list[CommitInfo],
    previous_stock: float = 0.0,
) -> TechDebtResult:
    """
    计算技术债利息率和存量

    此函数实现了两个层次的分析:

    1. 利息率 (横截面): 本周期内修复类代码占总代码的比例
       → 回答 "当前有多少精力在还利息?"

    2. 债务存量 (纵向): 基于存量/流量模型跟踪债务的累积
       → 回答 "债务总量是在增加还是减少?"
       new_debt = 非修复类变更量 (可能引入新债务)
       repay = 修复类变更量 (在偿还旧债)
       净变化 = new_debt × 0.1 - repay × 0.5
       (假设: 新功能代码有 10% 概率引入技术债, 修复代码有 50% 效率偿还债务)

    Args:
        commits: 本周期的代码提交列表
        previous_stock: 上一周期的技术债存量 (首次运行传 0)

    Returns:
        TechDebtResult: 包含利息率、存量和详细分析的结果
    """
    if not commits:
        return TechDebtResult(
            description="❓ 没有代码提交数据, 无法计算技术债。"
        )

    total_changes = 0
    fix_changes = 0
    fix_count = 0
    author_fix_counts: dict[str, int] = {}

    for commit in commits:
        change_size = commit.additions + commit.deletions
        total_changes += change_size

        if is_fix_commit(commit):
            fix_changes += change_size
            fix_count += 1
            author_fix_counts[commit.author] = (
                author_fix_counts.get(commit.author, 0) + 1
            )

    # === 利息率计算 ===
    # 优先按代码行数; 当 GitLab 未返回 stats 时 (total_changes=0) 用 commit 数量比例兜底
    if total_changes > 0:
        interest_rate = fix_changes / total_changes
    else:
        interest_rate = fix_count / max(len(commits), 1)
        logger.info(
            f"技术债: GitLab 未返回 commit stats, 使用 commit 数量比例兜底 "
            f"(fix={fix_count}, total={len(commits)}, rate={interest_rate:.3f})"
        )

    # === 债务等级判定 ===
    if interest_rate >= settings.TECH_DEBT_DANGER_THRESHOLD:
        level = "danger"
        desc = (
            f"🔴 技术债【危险】: 利息率 {interest_rate:.1%}, "
            f"超过 {settings.TECH_DEBT_DANGER_THRESHOLD:.0%} 的精力在修复旧代码。"
            "建议: 暂停新需求, 启动迁移/重构专项 (参考 2.6节)。"
        )
    elif interest_rate >= settings.TECH_DEBT_ALERT_THRESHOLD:
        level = "alert"
        desc = (
            f"🟠 技术债【告警】: 利息率 {interest_rate:.1%}, "
            f"超过 {settings.TECH_DEBT_ALERT_THRESHOLD:.0%} 精力在还利息。"
            "建议: 下个迭代减少 50% 需求流入, 集中偿债 (参考 2.5节)。"
        )
    elif interest_rate >= 0.15:
        level = "warning"
        desc = (
            f"🟡 技术债【需关注】: 利息率 {interest_rate:.1%}, "
            "债务开始侵蚀产能。建议: 监控趋势, 防止进一步恶化。"
        )
    else:
        level = "healthy"
        desc = (
            f"🟢 技术债【健康】: 利息率 {interest_rate:.1%}, "
            "大部分精力在创造新价值。"
        )

    # === 技术债存量计算 (Stocks & Flows) ===
    # 新功能代码可能引入技术债 (假设 10% 的概率)
    non_fix_changes = total_changes - fix_changes
    new_debt_flow = non_fix_changes * 0.1
    # 修复代码在偿还债务 (假设 50% 的偿还效率)
    repay_flow = fix_changes * 0.5
    debt_stock = max(0.0, previous_stock + new_debt_flow - repay_flow)

    # === 最大 "债务贡献者" (修复类 commit 最多的作者) ===
    # 注意: 这不是用来指责个人, 而是识别哪些人承担了最多的还债工作
    # 书 4.6节: 系统性解决, 不依赖个人英雄
    top_contributors = sorted(
        author_fix_counts.items(), key=lambda x: x[1], reverse=True
    )[:5]

    result = TechDebtResult(
        interest_rate=interest_rate,
        level=level,
        total_changes=total_changes,
        fix_changes=fix_changes,
        fix_commit_count=fix_count,
        total_commit_count=len(commits),
        debt_stock=debt_stock,
        top_debt_contributors=top_contributors,
        description=desc,
    )

    logger.info(
        f"技术债分析: interest_rate={interest_rate:.3f}, "
        f"level={level}, stock={debt_stock:.1f}"
    )

    return result
