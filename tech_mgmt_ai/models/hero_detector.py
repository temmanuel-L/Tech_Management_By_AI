"""
"英雄" 检测模型

═══════════════════════════════════════════════════════════════════════════════
理论依据: 《An Elegant Puzzle》4.6节 "消灭英雄, 努力工作并不能保证成功"
═══════════════════════════════════════════════════════════════════════════════

书中核心观点:
  - "英雄程序员" 以超长工时、个人突击换取短期进度, 但埋下隐患
  - 效率假象: 短期赶完任务, 但缺乏交接与复盘, 形成知识孤岛
  - 团队风险: 一旦英雄离开, 项目陷入 "断炊" 危机 (单点风险)
  - 解决方案: 通过合理分工、代码评审、轮值值班等机制分散知识

本模型使用 基尼系数 (Gini Coefficient) 衡量代码提交的集中度。

基尼系数是衡量不平等分布的经典指标, 原本用于收入分配研究。
在此语境下, 它衡量 "代码产出是否公平地分散在团队成员间"。

公式:
         2 · Σᵢ(i · xᵢ)     n + 1
  Gini = ―――――――――――――――――― - ―――――
           n · Σᵢ(xᵢ)          n

  其中:
    xᵢ = 第 i 个人的 commit 数 (按升序排列, i 从 1 开始)
    n  = 团队总人数

基尼系数取值范围 [0, 1]:
  0 → 完全平等: 每个人 commit 数相同
  1 → 完全不平等: 所有 commit 集中于一人

判定标准:
  Gini ≤ 0.4  → 健康: 代码产出分布均匀, 团队协作良好
  0.4 < Gini ≤ 0.6 → 中度集中: 需关注是否有成员负担过重
  Gini > 0.6  → 重度英雄依赖: 存在单点风险, 告警
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass, field

from tech_mgmt_ai.config import settings
from tech_mgmt_ai.connectors import CommitInfo

logger = logging.getLogger(__name__)


@dataclass
class HeroDetectionResult:
    """
    英雄检测分析结果

    Attributes:
        gini_coefficient: 基尼系数 (0.0-1.0)
        level: 告警等级 (healthy / warning / alert)
        team_size: 参与分析的团队人数
        commit_distribution: 每人的 commit 数量 {作者: 数量}
        top_contributors: commit 最多的前 5 人 [(作者, 数量)]
        description: 可读的分析描述
    """
    gini_coefficient: float = 0.0
    level: str = "healthy"
    team_size: int = 0
    commit_distribution: dict[str, int] = field(default_factory=dict)
    top_contributors: list[tuple[str, int]] = field(default_factory=list)
    description: str = ""


def calculate_gini(values: list[int]) -> float:
    """
    计算基尼系数

    实现了标准的基尼系数公式, 输入为非负整数列表 (如每人的 commit 数)。

    算法步骤:
      1. 将 values 按升序排列
      2. 计算加权累积和: Σ(i · xᵢ), i 从 1 开始
      3. 计算总和: Σ(xᵢ)
      4. 代入公式: Gini = 2·Σ(i·xᵢ) / (n·Σxᵢ) - (n+1)/n

    边界情况:
      - 空列表或全零: 返回 0.0
      - 单人团队: 返回 0.0 (无法评估分布)

    Args:
        values: 每人的 commit 数量列表

    Returns:
        基尼系数, 范围 [0.0, 1.0]
    """
    # 过滤零值并排序
    sorted_values = sorted(v for v in values if v >= 0)
    n = len(sorted_values)

    if n <= 1:
        return 0.0

    total = sum(sorted_values)
    if total == 0:
        return 0.0

    # 计算 Σ(i · xᵢ), i 从 1 开始
    weighted_sum = sum((i + 1) * x for i, x in enumerate(sorted_values))

    gini = (2.0 * weighted_sum) / (n * total) - (n + 1) / n
    return max(0.0, min(1.0, gini))  # 确保在 [0, 1] 范围内


def detect_heroes(commits: list[CommitInfo]) -> HeroDetectionResult:
    """
    检测团队中是否存在 "英雄" 式过度依赖

    此函数将代码提交数据转化为团队协作健康度的定量评估。

    书 4.6节 管理建议:
      - 重度英雄依赖时, 应通过轮值（书 1.1节）和代码评审分散知识
      - 不应简单地惩罚 "英雄", 而是改变系统使协作成为常态
      - 通过结对编程、知识分享会 (书 2.15节) 降低知识集中度

    Args:
        commits: 代码提交列表

    Returns:
        HeroDetectionResult: 包含基尼系数、告警等级和分布详情
    """
    if not commits:
        return HeroDetectionResult(
            description="❓ 没有代码提交数据, 无法进行英雄检测。"
        )

    # 统计每人的 commit 数量
    author_counts: dict[str, int] = {}
    for commit in commits:
        author_counts[commit.author] = author_counts.get(commit.author, 0) + 1

    team_size = len(author_counts)

    if team_size <= 1:
        return HeroDetectionResult(
            gini_coefficient=0.0,
            level="healthy",
            team_size=team_size,
            commit_distribution=author_counts,
            description="ℹ️ 团队仅有一人, 无法评估提交集中度。",
        )

    # 计算基尼系数
    gini = calculate_gini(list(author_counts.values()))

    # 等级判定
    if gini > settings.HERO_GINI_ALERT_THRESHOLD:
        level = "alert"
        desc = (
            f"🔴 英雄检测【告警】: 基尼系数 {gini:.3f} > {settings.HERO_GINI_ALERT_THRESHOLD}, "
            f"代码提交高度集中于少数人, 存在严重的单点风险。\n"
            "建议:\n"
            "  1. 推行结对编程和代码评审, 分散知识 (参考 2.15节)\n"
            "  2. 建立轮值机制, 避免一人长期负责关键模块 (参考 1.1节)\n"
            "  3. 关注 '英雄' 的工作负荷, 防止倦怠 (参考 4.6节)"
        )
    elif gini > settings.HERO_GINI_WARNING_THRESHOLD:
        level = "warning"
        desc = (
            f"🟡 英雄检测【提醒】: 基尼系数 {gini:.3f}, "
            "代码提交存在一定的集中趋势, 需关注。"
        )
    else:
        level = "healthy"
        desc = (
            f"🟢 英雄检测【健康】: 基尼系数 {gini:.3f}, "
            "代码产出分布均匀, 团队协作良好。"
        )

    # 排行榜 (commit 最多的前 5 人)
    top_contributors = sorted(
        author_counts.items(), key=lambda x: x[1], reverse=True
    )[:5]

    logger.info(
        f"英雄检测: gini={gini:.3f}, level={level}, "
        f"team_size={team_size}"
    )

    return HeroDetectionResult(
        gini_coefficient=gini,
        level=level,
        team_size=team_size,
        commit_distribution=author_counts,
        top_contributors=top_contributors,
        description=desc,
    )
