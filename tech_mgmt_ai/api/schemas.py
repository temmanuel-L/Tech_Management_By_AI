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
    description: str = ""


class HealthScoreResponse(BaseModel):
    """综合健康分"""
    score: float = 0.0
    level: str = "unknown"
    dora_contribution: float = 0.0
    debt_contribution: float = 0.0
    hero_contribution: float = 0.0
    state_contribution: float = 0.0


class AnalyzeResponse(BaseModel):
    """完整分析结果"""
    health: HealthScoreResponse
    dora: DORAMetricsResponse
    tech_debt: TechDebtResponse
    hero: HeroResponse
    team_state: TeamStateResponse
    report_markdown: str = ""
    created_at: str = ""


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
