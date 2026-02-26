"""
团队四状态诊断模型

═══════════════════════════════════════════════════════════════════════════════
理论依据: 《An Elegant Puzzle》1.2节 "把握团队的4种状态"
═══════════════════════════════════════════════════════════════════════════════

书中定义团队有四种动态状态:
  1. Falling Behind (落后): 积压工作多、士气低、用户满意度差
  2. Treading Water  (停滞): 能完成关键任务, 但无余力处理技术债
  3. Paying Down Debt(偿债): 主动偿还技术债, 节奏相对稳定
  4. Innovating      (创新): 技术债持续减少, 专注新需求和产品创新

书中未给出量化公式, 本模块基于书中描述的状态特征, 结合 DORA 研究和
系统动力学思想, 构建了一个多维加权评分模型:

  状态得分 S = w₁·backlog_trend + w₂·debt_ratio + w₃·morale_proxy + w₄·innovation_ratio

各维度计算方式:
  - backlog_trend:   (本周关闭 - 本周新增) / max(总积压, 1)
                     正值表示积压在减少, 负值表示在增加
  - debt_ratio:      -(debt_tasks / max(total_tasks, 1))
                     取负值, 因为债务越高对状态越不利
  - morale_proxy:    reviews_given / max(team_size, 1)
                     Code Review 参与度作为士气的间接指标
  - innovation_ratio: feature_tasks / max(total_tasks, 1)
                     新功能占比越高, 说明团队越接近创新状态

权重默认值 (可通过 settings 调整):
  w_backlog=0.30, w_debt=0.25, w_morale=0.20, w_innovation=0.25

状态判定阈值:
  S < -0.3           → Falling Behind
  -0.3 ≤ S < 0.0     → Treading Water
  0.0 ≤ S < 0.3      → Paying Down Debt
  S ≥ 0.3            → Innovating
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

from tech_mgmt_ai.config import settings

logger = logging.getLogger(__name__)


class TeamState(StrEnum):
    """
    团队四种状态枚举

    状态之间的跃迁路径通常为:
    Falling Behind → Treading Water → Paying Down Debt → Innovating

    但在外部压力 (如需求激增、人员流失) 下, 团队可能发生跃退。
    管理者应优先干预 Falling Behind 的团队 (参考 1.2节)。
    """
    FALLING_BEHIND = "falling_behind"     # 落后: 积压增长, 急需外部支援
    TREADING_WATER = "treading_water"     # 停滞: 勉强维持, 无力偿债
    PAYING_DOWN_DEBT = "paying_down_debt"  # 偿债: 主动还债, 节奏稳定
    INNOVATING = "innovating"             # 创新: 债务低, 聚焦新需求


@dataclass
class TeamStateInput:
    """
    团队状态评估的输入数据

    这些数据来自感知层 (connectors) 和认知层 (llm), 由指标引擎汇整后传入。
    """
    # 本周期新增任务数
    tasks_created: int = 0
    # 本周期关闭/完成的任务数
    tasks_closed: int = 0
    # 当前未关闭的总积压任务数
    total_backlog: int = 0
    # 被分类为 "修复/债务" 的任务数
    debt_tasks: int = 0
    # 被分类为 "功能" 的任务数
    feature_tasks: int = 0
    # 本周期总任务数 (用于计算比例)
    total_tasks: int = 0
    # 本周期团队成员给出的 Code Review 评论数
    reviews_given: int = 0
    # 当前团队人数
    team_size: int = 1


@dataclass
class TeamStateResult:
    """
    团队状态评估结果

    包含状态判定、原始分数以及各维度得分, 便于管理者理解诊断依据。
    """
    state: TeamState              # 判定的团队状态
    score: float                 # 综合得分 S
    backlog_score: float         # 积压趋势维度得分
    debt_score: float            # 技术债维度得分
    morale_score: float          # 士气代理维度得分
    innovation_score: float      # 创新占比维度得分
    description: str             # 可读的状态描述


def diagnose_team_state(data: TeamStateInput) -> TeamStateResult:
    """
    诊断团队当前所处状态

    本函数实现了书 1.2 节的 "状态—干预—跃迁" 循环中的 "状态" 诊断步骤。
    管理者获取诊断结果后, 应根据状态匹配对应的干预策略:
      - Falling Behind: 增加人手或缩小工作范围
      - Treading Water:  引入资源或调整目标优先级
      - Paying Down Debt: 持续支持, 避免回退
      - Innovating:      保持稳定, 避免不当重组 (参考 1.3节)

    Args:
        data: 来自连接器和 LLM 分析的团队数据

    Returns:
        TeamStateResult: 包含状态、分数和各维度明细的诊断结果
    """
    # === 维度 1: 积压趋势 ===
    # 含义: 团队消化需求的速度是否跟得上流入
    # 正值 → 积压在减少 (好), 负值 → 积压在增长 (差)
    net_throughput = data.tasks_closed - data.tasks_created
    backlog_denom = max(data.total_backlog, 1)  # 避免除零
    backlog_score = net_throughput / backlog_denom

    # === 维度 2: 技术债占比 ===
    # 含义: 修复/偿债类任务占总量的比例, 取负值表示越高越不利
    total = max(data.total_tasks, 1)
    debt_score = -(data.debt_tasks / total)

    # === 维度 3: 士气代理 (Code Review 参与度) ===
    # 含义: 人均 Review 评论数, 越高表示团队协作越活跃
    # 书 2.15节: 建立学习共同体, 让新老成员相互学习
    team = max(data.team_size, 1)
    morale_score = data.reviews_given / team
    # 归一化到 [-1, 1] 区间, 假设人均 5 条Review为满分
    morale_score = min(morale_score / 5.0, 1.0)

    # === 维度 4: 创新占比 ===
    # 含义: Feature 类任务占总量的比例
    innovation_score = data.feature_tasks / total

    # === 加权综合得分 ===
    score = (
        settings.TEAM_STATE_W_BACKLOG * backlog_score
        + settings.TEAM_STATE_W_DEBT * debt_score
        + settings.TEAM_STATE_W_MORALE * morale_score
        + settings.TEAM_STATE_W_INNOVATION * innovation_score
    )

    # === 状态判定 ===
    if score < settings.TEAM_STATE_THRESHOLD_FALLING_BEHIND:
        state = TeamState.FALLING_BEHIND
        description = (
            "⚠️ 团队处于【落后】状态: 积压增长、技术债高企。"
            "建议: 增加人手或缩小工作范围, 优先稳定核心系统。"
            "(参考 1.2节: 管理者应优先干预落后团队)"
        )
    elif score < 0.0:
        state = TeamState.TREADING_WATER
        description = (
            "🔄 团队处于【停滞】状态: 能完成关键任务, 但无余力处理技术债。"
            "建议: 引入额外资源或调整优先级, 避免长期停留在此状态。"
        )
    elif score < settings.TEAM_STATE_THRESHOLD_INNOVATING:
        state = TeamState.PAYING_DOWN_DEBT
        description = (
            "📈 团队处于【偿债】状态: 正在主动偿还技术债, 节奏逐步稳定。"
            "建议: 持续支持并保持当前节奏, 避免引入大规模变更。"
        )
    else:
        state = TeamState.INNOVATING
        description = (
            "🚀 团队处于【创新】状态: 技术债持续减少, 聚焦新需求和产品创新。"
            "建议: 保持团队稳定, 避免不当人员重组 (参考 1.3节)。"
        )

    logger.info(f"团队状态诊断: {state.value} (score={score:.3f})")

    return TeamStateResult(
        state=state,
        score=score,
        backlog_score=backlog_score,
        debt_score=debt_score,
        morale_score=morale_score,
        innovation_score=innovation_score,
        description=description,
    )
