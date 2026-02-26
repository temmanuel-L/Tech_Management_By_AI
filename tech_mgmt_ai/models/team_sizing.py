"""
团队规模校准模型

═══════════════════════════════════════════════════════════════════════════════
理论依据: 《An Elegant Puzzle》1.1节 "4个原则确定团队规模"
═══════════════════════════════════════════════════════════════════════════════

四个互相关联的原则:

  1. 经理-工程师比例: 一名经理最有效的管理范围是 6-8 名工程师
     过少 → 微观管理, 过多 → 沟通链过长

  2. 高级经理-经理比例: 高级经理应直接管理 4-6 名经理
     确保仍有精力进行组织建设、战略规划与跨团队协同

  3. 待命轮值: 需要 ≥ 8 名工程师轮值承担生产支持
     如果轮值压力过大, 说明团队该拆分或增员

  4. 小团队可行性: < 4 人的 "小队" 难以形成团队文化
     易因成员离职而陷入技术债与知识孤岛

所有阈值可通过 settings 中的 TEAM_SIZING_* 环境变量调整。
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass, field

from tech_mgmt_ai.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TeamSizingIssue:
    """单条规模校准问题"""
    rule: str           # 违反的规则名称
    severity: str       # 严重程度: info / warning / alert
    current_value: float  # 当前值
    expected_range: str   # 期望范围
    suggestion: str       # 改进建议


@dataclass
class TeamSizingResult:
    """
    团队规模校准结果

    Attributes:
        is_healthy: 所有规则是否都通过
        issues: 发现的问题列表
        description: 可读的综合描述
    """
    is_healthy: bool = True
    issues: list[TeamSizingIssue] = field(default_factory=list)
    description: str = ""


def check_team_sizing(
    engineers: int,
    managers: int,
    directors: int = 0,
    oncall_pool_size: int = 0,
) -> TeamSizingResult:
    """
    检查当前组织结构是否符合书中的四个规模原则

    此函数将书中定性的组织设计原则转化为可量化的校准检查。

    使用场景 (书中映射):
      - 规划新团队时 (1.1节)
      - 人员重组前 (1.3节): 先检查重组后的组织是否符合原则
      - 高速增长期 (1.4节): 监控团队规模是否超出健康范围

    Args:
        engineers: 工程师人数
        managers: 经理人数
        directors: 高级经理/总监人数 (可选)
        oncall_pool_size: 值班轮值池人数 (可选)

    Returns:
        TeamSizingResult: 包含是否健康、问题列表和改进建议
    """
    issues: list[TeamSizingIssue] = []

    # === 规则 1: 经理-工程师比例 ===
    if managers > 0:
        ratio = engineers / managers
        min_r = settings.TEAM_SIZING_MGR_ENG_MIN
        max_r = settings.TEAM_SIZING_MGR_ENG_MAX

        if ratio < min_r:
            issues.append(TeamSizingIssue(
                rule="经理-工程师比例",
                severity="warning",
                current_value=ratio,
                expected_range=f"1:{min_r} ~ 1:{max_r}",
                suggestion=(
                    f"当前比例 1:{ratio:.1f}, 低于建议的 1:{min_r}。"
                    "经理可能在微观管理, 考虑合并团队或减少经理数量。"
                ),
            ))
        elif ratio > max_r:
            issues.append(TeamSizingIssue(
                rule="经理-工程师比例",
                severity="alert",
                current_value=ratio,
                expected_range=f"1:{min_r} ~ 1:{max_r}",
                suggestion=(
                    f"当前比例 1:{ratio:.1f}, 高于建议的 1:{max_r}。"
                    "经理可能无法充分指导团队, 考虑增加经理或拆分团队。"
                ),
            ))

    # === 规则 2: 高级经理-经理比例 ===
    if directors > 0 and managers > 0:
        ratio = managers / directors
        min_r = settings.TEAM_SIZING_DIR_MGR_MIN
        max_r = settings.TEAM_SIZING_DIR_MGR_MAX

        if ratio < min_r:
            issues.append(TeamSizingIssue(
                rule="高级经理-经理比例",
                severity="info",
                current_value=ratio,
                expected_range=f"1:{min_r} ~ 1:{max_r}",
                suggestion=(
                    f"当前比例 1:{ratio:.1f}。"
                    "高级经理管理的经理较少, 可能有更多精力投入战略规划。"
                ),
            ))
        elif ratio > max_r:
            issues.append(TeamSizingIssue(
                rule="高级经理-经理比例",
                severity="warning",
                current_value=ratio,
                expected_range=f"1:{min_r} ~ 1:{max_r}",
                suggestion=(
                    f"当前比例 1:{ratio:.1f}, 高于建议的 1:{max_r}。"
                    "高级经理可能无力兼顾战略规划与协同, 考虑增加高级经理。"
                ),
            ))

    # === 规则 3: 团队最小人数 ===
    total_team = engineers + managers
    if total_team < settings.TEAM_SIZING_MIN_TEAM_SIZE:
        issues.append(TeamSizingIssue(
            rule="团队最小人数",
            severity="alert",
            current_value=total_team,
            expected_range=f"≥ {settings.TEAM_SIZING_MIN_TEAM_SIZE}",
            suggestion=(
                f"团队仅 {total_team} 人, 低于 {settings.TEAM_SIZING_MIN_TEAM_SIZE} 人。"
                "难以形成团队文化, 建议通过新组建或并队方式调整。"
            ),
        ))

    # === 规则 4: 值班轮值人数 ===
    if oncall_pool_size > 0 and oncall_pool_size < settings.TEAM_SIZING_MIN_ONCALL_SIZE:
        issues.append(TeamSizingIssue(
            rule="值班轮值人数",
            severity="warning",
            current_value=oncall_pool_size,
            expected_range=f"≥ {settings.TEAM_SIZING_MIN_ONCALL_SIZE}",
            suggestion=(
                f"值班池仅 {oncall_pool_size} 人, 低于 {settings.TEAM_SIZING_MIN_ONCALL_SIZE} 人。"
                "轮值压力过大, 考虑增员或跨团队共享值班。"
            ),
        ))

    is_healthy = len(issues) == 0
    desc_parts = []
    if is_healthy:
        desc_parts.append("✅ 团队规模校准: 所有原则均符合 (参考 1.1节)")
    else:
        desc_parts.append(f"⚠️ 团队规模校准: 发现 {len(issues)} 个问题")
        for issue in issues:
            desc_parts.append(f"  [{issue.severity}] {issue.rule}: {issue.suggestion}")

    logger.info(f"团队规模校准: healthy={is_healthy}, issues={len(issues)}")

    return TeamSizingResult(
        is_healthy=is_healthy,
        issues=issues,
        description="\n".join(desc_parts),
    )
