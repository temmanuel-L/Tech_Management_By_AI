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
  w_backlog=0.20, w_debt=0.20, w_morale=0.20, w_innovation=0.20, w_creating_debt=0.20

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
    # LLM 代码质量评分 (1-10)，用于代码健康度维度
    llm_quality_score: float | None = None
    # LLM 判定为引入技术债的 MR/Commit 数量
    llm_creating_debt_count: int = 0
    # LLM 判定为偿还技术债的 MR/Commit 数量
    llm_paying_debt_count: int = 0
    # LLM 审查总数 (MR + Commit 抽样)
    llm_total_reviews: int = 0
    # LLM 判定为新增业务功能的 MR/Commit 数量（用于创新占比维度）
    llm_adding_new_function_count: int = 0
    # 本周期已合并的 MR 数 (无 Issues 时用作积压/交付代理)
    mr_merged_count: int = 0
    # 本周期总 MR 数
    total_mr_count: int = 0


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
    creating_debt_score: float = 0.0  # 新增技术债维度 (取负, 越高越不利)
    calc_explanation: str = ""   # 得分计算逻辑说明
    score_ranges: str = ""       # 各状态对应的得分区间
    llm_enhanced: bool = False # 是否使用了 LLM 增强


def _debt_ratio_to_score(ratio: float) -> float:
    """
    偿债占比 → 子指标得分 [-1, 1]
    峰值在 0.4: f(0.4)=1; f(0)=-0.1; f(1)=-1
    [0, 0.4] 单调增, (0.4, 1] 单调减
    """
    ratio = max(0.0, min(1.0, ratio))
    if ratio <= 0.4:
        return -0.1 + 1.1 * (ratio / 0.4) if ratio > 0 else -0.1
    return 1.0 - 2.0 * (ratio - 0.4) / 0.6


def _creating_debt_ratio_to_score(ratio: float) -> float:
    """
    新增技术债占比 → 得分 非线性映射到 [-1, 0.5]

    锚点（以 8 抽样为例）: 0→0.5, 1个→0.2, 2个→0, 3个→-0.2, 全部→-1，
    放大新增债数量的惩罚、使分值随占比快速下降。
    """
    r = max(0.0, min(1.0, ratio))
    if r <= 0.125:  # [0, 1/8]
        return 0.5 - 2.4 * r
    if r <= 0.25:   # (1/8, 2/8]
        return 0.2 - 1.6 * (r - 0.125)
    if r <= 0.375:  # (2/8, 3/8]
        return -1.6 * (r - 0.25)
    # (3/8, 1]: -0.2 线性到 -1
    return -0.2 - 0.8 * (r - 0.375) / 0.625


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
    # === 维度 1: 积压趋势 值域约[-1,1] ===
    # 有 Issues 时: (关闭-新增)/积压; 无 Issues 时以 MR 合并率为代理，采用中性化公式避免长期满分
    # 参考: 合并率 85% 视为中性(0)，100%→约 0.3，50%→约 -0.7，避免“全部合并即满分 1.0”
    if data.total_backlog > 0:
        net_throughput = data.tasks_closed - data.tasks_created
        backlog_denom = max(data.total_backlog, 1)
        backlog_score = max(-1.0, min(1.0, net_throughput / backlog_denom))
    elif data.total_mr_count > 0:
        merge_rate = data.mr_merged_count / max(data.total_mr_count, 1)
        # 中性基线 0.85: 高于 85% 合并率为正，低于为负，最高约 0.3 而非 1.0
        backlog_score = max(-1.0, min(1.0, (merge_rate - 0.85) * 2.0))
    else:
        backlog_score = 0.0

    # === 维度 2: 偿债占比 非线性 [0,1]→[-1,1], 峰值 0.4 ===
    # 0.4 最优(1), 0 或 1 较差; [0,0.4] 单调增, (0.4,1] 单调减
    total = max(data.total_tasks, 1)
    if data.llm_total_reviews > 0:
        pay_ratio = data.llm_paying_debt_count / data.llm_total_reviews
    else:
        pay_ratio = data.debt_tasks / total  # Issues 债务任务占比, 同曲线
    debt_score = _debt_ratio_to_score(pay_ratio)

    # === 维度 3: 士气 值域[-1,1] (2×归一化-1) ===
    team = max(data.team_size, 1)
    raw_morale = min(data.reviews_given / team / 5.0, 1.0)
    morale_score = 2.0 * raw_morale - 1.0

    # === 维度 4: 创新占比 值域[-0.5, 1] 非线性映射 ===
    # 占比 0→-0.5，约 10–20%→0，100%→1；5/8 等高占比映射到 ≥0.5
    if data.llm_total_reviews > 0:
        raw_innovation = data.llm_adding_new_function_count / data.llm_total_reviews
    else:
        raw_innovation = data.feature_tasks / total
    raw_innovation = max(0.0, min(1.0, raw_innovation))
    if raw_innovation <= 0.15:
        innovation_score = -0.5 + (0.5 / 0.15) * raw_innovation  # [0, 0.15] → [-0.5, 0]
    else:
        innovation_score = (raw_innovation - 0.15) / 0.85  # (0.15, 1] → (0, 1]

    # === 维度 5: 新增技术债任务占比 值域[-1, 0.5] 非线性 (0→0.5, 1/8→0.2, 2/8→0, 3/8→-0.2, 全部→-1) ===
    if data.llm_total_reviews > 0:
        raw_creating = data.llm_creating_debt_count / data.llm_total_reviews
        creating_debt_score = _creating_debt_ratio_to_score(raw_creating)
    else:
        creating_debt_score = 0.0

    # === 加权综合得分 (五维权重和=1, S 约在 [-1,1]) ===
    score = (
        settings.TEAM_STATE_W_BACKLOG * backlog_score
        + settings.TEAM_STATE_W_DEBT * debt_score
        + settings.TEAM_STATE_W_MORALE * morale_score
        + settings.TEAM_STATE_W_INNOVATION * innovation_score
        + settings.TEAM_STATE_W_CREATING_DEBT * creating_debt_score
    )

    # === 计算逻辑说明与得分区间 ===
    score_ranges = (
        "得分区间: 落后 S<-0.3 | 停滞 -0.3≤S<0 | 偿债 0≤S<0.3 | 创新 S≥0.3"
    )
    parts = [
        f"积压趋势×{settings.TEAM_STATE_W_BACKLOG:.0%}",
        f"偿债占比×{settings.TEAM_STATE_W_DEBT:.0%}",
        f"士气×{settings.TEAM_STATE_W_MORALE:.0%}",
        f"创新占比×{settings.TEAM_STATE_W_INNOVATION:.0%}",
        f"新增技术债任务占比×{settings.TEAM_STATE_W_CREATING_DEBT:.0%}",
    ]
    calc_explanation = f"S = {' + '.join(parts)} | 当前: 积压={backlog_score:.3f} 偿债={debt_score:.3f} 士气={morale_score:.3f} 创新={innovation_score:.3f} 新增债占比={creating_debt_score:.3f}"
    calc_explanation += f" → S={score:.3f}"

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
        creating_debt_score=creating_debt_score,
        description=description,
        calc_explanation=calc_explanation,
        score_ranges=score_ranges,
        llm_enhanced=data.llm_quality_score is not None or data.llm_total_reviews > 0,
    )
