"""
Pydantic 响应模型

定义 API 返回的 JSON 结构, 前端据此渲染组件。
"""

from pydantic import BaseModel, Field


class DORAMetricsResponse(BaseModel):
    """DORA 四指标"""
    lead_time_hours: float = 0.0
    deploy_frequency: float = 0.0
    change_failure_rate: float = 0.0
    mttr_hours: float = 0.0
    overall_score: float = 0.0
    overall_level: str = "low"


class TechDebtResponse(BaseModel):
    """技术债"""
    interest_rate: float = 0.0
    level: str = "healthy"
    stock: float = 0.0
    fix_commit_count: int = 0
    total_commit_count: int = 0
    llm_enhanced: bool = False
    llm_paying_debt_count: int = 0
    llm_creating_debt_count: int = 0
    llm_reviewed_mr_count: int = 0
    llm_reviewed_commit_count: int = 0
    interest_rate_calc_note: str = ""


class HeroResponse(BaseModel):
    """英雄检测"""
    gini_coefficient: float = 0.0
    level: str = "healthy"
    team_size: int = 0
    top_contributors: list[dict] = Field(default_factory=list)


class TeamStateResponse(BaseModel):
    """团队状态"""
    state: str = "unknown"
    score: float = 0.0
    backlog_score: float = 0.0
    debt_score: float = 0.0
    morale_score: float = 0.0
    innovation_score: float = 0.0
    creating_debt_score: float = 0.0
    description: str = ""
    calc_explanation: str = ""
    score_ranges: str = ""
    llm_enhanced: bool = False


class HealthScoreResponse(BaseModel):
    """综合健康分"""
    score: float = 0.0
    level: str = "unknown"
    # 维度原始得分 (0-100, 不含权重)
    dora_score: float = 0.0
    debt_score: float = 0.0
    hero_score: float = 0.0
    state_score: float = 0.0
    # 维度贡献分 (已乘以权重)
    dora_contribution: float = 0.0
    debt_contribution: float = 0.0
    hero_contribution: float = 0.0
    state_contribution: float = 0.0
    # 各维度权重 (0-1)
    w_dora: float = 0.0
    w_debt: float = 0.0
    w_hero: float = 0.0
    w_state: float = 0.0


class CommitReviewItem(BaseModel):
    """单条 Commit/MR 审查结果（用于数据下钻）"""
    mr_id: int = 0
    sha: str = ""
    author: str = ""  # 作者（GitLab username）
    message: str = ""  # Commit message 或 MR title
    diff: str = ""  # 代码 diff（可能较长）
    quality_score: int = 5
    is_paying_debt: bool = False
    is_paying_debt_reason: str = ""
    is_creating_debt: bool = False
    is_creating_debt_reason: str = ""
    is_creating_debt_code_block: str = ""
    is_creating_debt_correct_action: str = ""
    is_adding_new_function: bool = False
    is_adding_new_function_reason: str = ""
    summary: str = ""


class AnalyzeResponse(BaseModel):
    """完整分析结果"""
    health: HealthScoreResponse
    dora: DORAMetricsResponse
    tech_debt: TechDebtResponse
    hero: HeroResponse
    team_state: TeamStateResponse
    report_markdown: str = ""
    created_at: str = ""
    # 用于数据下钻: LLM 审查结果（前端可缓存用于下钻页面）
    llm_reviews: list[CommitReviewItem] = []
    # 各项目 commit 数量统计（用于 Dashboard 展示）
    project_commit_counts: list[dict] = []


class HistoryPointResponse(BaseModel):
    """历史数据点 (用于趋势图)"""
    created_at: str
    health_score: float
    dora_overall_score: float
    tech_debt_interest_rate: float
    hero_gini_coefficient: float
    team_state: str


class TeamSizingRequest(BaseModel):
    """团队规模校准请求"""
    engineers: int
    managers: int
    directors: int = 0
    oncall_pool_size: int = 0


class SampleInfo(BaseModel):
    """抽样信息"""
    sample_method: str = ""  # 抽样方法说明
    sample_count: int = 0  # 抽样数量
    total_count: int = 0  # 总量
    source: str = ""  # 数据来源: "llm" 或 "keyword"


class DrillDownResponse(BaseModel):
    """团队状态数据下钻结果"""
    sample_info: SampleInfo
    all_samples: list[CommitReviewItem]  # 所有被审查的 commit 列表
    filtered_items: list[CommitReviewItem]  # 符合条件的 commit（如 is_paying_debt=True）
    total_count: int = 0  # 符合筛选条件的总数


class TeamSizingIssueResponse(BaseModel):
    """规模问题"""
    rule: str
    severity: str
    current_value: float
    expected_range: str
    suggestion: str


class TeamSizingResponse(BaseModel):
    """团队规模校准结果"""
    is_healthy: bool
    issues: list[TeamSizingIssueResponse] = Field(default_factory=list)
    description: str = ""
