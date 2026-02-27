"""
全局配置管理

设计模式参考: agent-service-toolkit-for-lobechat/src/core/settings.py
使用 pydantic-settings 从 .env 文件和环境变量加载配置。
所有数学模型的系数均在此集中管理, 每个系数附有详细的书籍章节引用。
"""

from typing import Any

from dotenv import find_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from tech_mgmt_ai.schema.models import (
    AllModelEnum,
    AnthropicModelName,
    DeepseekModelName,
    OllamaModelName,
    OpenAICompatibleName,
    OpenAIModelName,
    Provider,
    ZhipuModelName,
)


class Settings(BaseSettings):
    """
    AI 技术管理工具全局配置

    所有配置项均可通过 .env 文件或环境变量覆盖。
    数学模型系数按「书籍章节 → 模块」组织, 便于理解每个参数的管理学背景。
    """

    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_default=False,
    )

    # =========================================================================
    # 基础配置
    # =========================================================================
    LOG_LEVEL: str = "INFO"

    # =========================================================================
    # GitLab 连接器
    # =========================================================================
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: SecretStr | None = None
    # 逗号分隔的项目 ID 列表, 如 "123,456"
    GITLAB_PROJECT_IDS: str = ""
    # 作者别名映射: 同一人可能在不同项目/机器用不同 git user.name
    # 格式: "别名1|别名2|别名3:规范名, 别名4|别名5:规范名2"
    # 例: "lwh14|刘文浩|lwh:刘文浩, uyplayer|热克甫:热克甫"
    GITLAB_AUTHOR_ALIASES: str = ""

    # =========================================================================
    # LLM 服务配置 — 多服务商适配
    # 设计思路: 通过 LLM_PROVIDER 指定主服务商, model_post_init 自动检测可用模型
    # =========================================================================
    LLM_PROVIDER: str = "openai"

    # --- OpenAI ---
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # --- Deepseek ---
    DEEPSEEK_API_KEY: SecretStr | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # --- 智谱 GLM ---
    ZHIPU_API_KEY: SecretStr | None = None

    # --- Anthropic Claude ---
    ANTHROPIC_API_KEY: SecretStr | None = None

    # --- Ollama (本地模型) ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str | None = None

    # --- OpenAI 兼容接口 ---
    COMPATIBLE_API_KEY: SecretStr | None = None
    COMPATIBLE_BASE_URL: str | None = None
    COMPATIBLE_MODEL: str | None = None

    # 自动检测结果 (由 model_post_init 填充)
    DEFAULT_MODEL: AllModelEnum | None = None  # type: ignore[assignment]
    AVAILABLE_MODELS: set[AllModelEnum] = Field(default_factory=set)  # type: ignore[assignment]

    # =========================================================================
    # 飞书配置 (项目管理数据源 + 告警通知)
    # =========================================================================
    FEISHU_APP_ID: str | None = None
    FEISHU_APP_SECRET: SecretStr | None = None
    FEISHU_WEBHOOK_URL: str | None = None

    # =========================================================================
    # 钉钉配置 (备选通知渠道)
    # =========================================================================
    DINGTALK_WEBHOOK_URL: str | None = None
    DINGTALK_SECRET: SecretStr | None = None

    # =========================================================================
    # 数学模型系数 — 团队状态诊断模型
    # 参考: 《An Elegant Puzzle》1.2节 "把握团队的4种状态"
    #
    # 团队状态由4个维度的加权评分决定:
    #   S = w_backlog·backlog_trend + w_debt·debt_ratio
    #     + w_morale·morale_proxy + w_innovation·innovation_ratio
    #
    # 状态判定:
    #   S < threshold_falling_behind         → Falling Behind (落后)
    #   threshold_falling_behind ≤ S < 0     → Treading Water (停滞)
    #   0 ≤ S < threshold_innovating         → Paying Down Debt (偿债)
    #   S ≥ threshold_innovating             → Innovating (创新)
    # =========================================================================

    # 五维权重 (含代码健康时共六维), 总和=1.0
    # 各子指标值域: 积压约[-1,1], 偿债/士气/创新[0,1], 新增债[-1,0], 代码健康[0,1]
    TEAM_STATE_W_BACKLOG: float = 0.25
    TEAM_STATE_W_DEBT: float = 0.20
    TEAM_STATE_W_MORALE: float = 0.15
    TEAM_STATE_W_INNOVATION: float = 0.20
    TEAM_STATE_W_CREATING_DEBT: float = 0.10
    TEAM_STATE_W_CODE_HEALTH: float = 0.10  # 有 LLM 时参与, 无时用 0.5 中性

    # 状态判定阈值
    TEAM_STATE_THRESHOLD_FALLING_BEHIND: float = -0.3
    TEAM_STATE_THRESHOLD_INNOVATING: float = 0.3

    # =========================================================================
    # 数学模型系数 — 技术债利息率模型
    # 参考: 《An Elegant Puzzle》2.5节 & 2.6节
    #
    # 利息率 I = fix_commit_changes / total_commit_changes
    # 当 I > alert_threshold 时, 表明团队过多精力在还利息
    # =========================================================================

    # 告警阈值: 超过 30% 精力在 "还利息", 应考虑集中偿债
    TECH_DEBT_ALERT_THRESHOLD: float = 0.30
    # 危险阈值: 超过 50% 表明债务已严重影响生产力
    TECH_DEBT_DANGER_THRESHOLD: float = 0.50
    # 识别修复类 Commit 的关键词 (逗号分隔)
    TECH_DEBT_FIX_KEYWORDS: str = "fix,bugfix,hotfix,patch,repair,resolve"
    # LLM 增强利息率时的权重 (0-1), 越大越偏向 LLM 判断
    TECH_DEBT_LLM_WEIGHT: float = 0.60
    # 每次分析中, 参与 LLM 抽样审查的最大 MR 数量 (异步并发, 可适当提高)
    TECH_DEBT_LLM_MR_SAMPLE_LIMIT: int = 2
    # 每次分析中, 参与 LLM 抽样审查的最大 Commit 数量 (异步并发, 可支持几十个)
    TECH_DEBT_LLM_COMMIT_SAMPLE_LIMIT: int = 3

    # =========================================================================
    # 数学模型系数 — DORA 指标
    # 参考: 《An Elegant Puzzle》2.1节, 《Accelerate》(Nicole Forsgren 等)
    #
    # 四个关键指标, 每个指标有 Elite/High/Medium/Low 四个等级
    # =========================================================================

    # Lead Time (变更前置时间) 阈值, 单位: 小时
    DORA_LEAD_TIME_ELITE_HOURS: float = 24       # < 1天 = Elite
    DORA_LEAD_TIME_HIGH_HOURS: float = 168        # < 7天 = High
    DORA_LEAD_TIME_MEDIUM_HOURS: float = 720      # < 30天 = Medium

    # Deployment Frequency (部署频率) 阈值, 单位: 次/天
    DORA_DEPLOY_FREQ_ELITE_PER_DAY: float = 1.0   # ≥ 1次/天 = Elite
    DORA_DEPLOY_FREQ_HIGH_PER_DAY: float = 0.143   # ≥ 1次/周 = High
    DORA_DEPLOY_FREQ_MEDIUM_PER_DAY: float = 0.033  # ≥ 1次/月 = Medium

    # Change Failure Rate (变更失败率) 阈值, 0.0-1.0
    DORA_CFR_ELITE: float = 0.05     # < 5% = Elite
    DORA_CFR_HIGH: float = 0.10      # < 10% = High
    DORA_CFR_MEDIUM: float = 0.15    # < 15% = Medium

    # MTTR (平均恢复时间) 阈值, 单位: 小时
    DORA_MTTR_ELITE_HOURS: float = 1       # < 1小时 = Elite
    DORA_MTTR_HIGH_HOURS: float = 24       # < 1天 = High
    DORA_MTTR_MEDIUM_HOURS: float = 168     # < 7天 = Medium

    # =========================================================================
    # 数学模型系数 — 英雄检测模型
    # 参考: 《An Elegant Puzzle》4.6节 "消灭英雄"
    #
    # 使用基尼系数衡量代码提交集中度:
    #   Gini = (2·Σ(i·x_i)) / (n·Σ(x_i)) - (n+1)/n
    # =========================================================================

    # 重度英雄依赖: 基尼系数 > 0.6, 代码提交高度集中, 存在单点风险
    HERO_GINI_ALERT_THRESHOLD: float = 0.6
    # 中度集中: 基尼系数 > 0.4, 提醒关注
    HERO_GINI_WARNING_THRESHOLD: float = 0.4

    # =========================================================================
    # 数学模型系数 — 团队规模校准模型
    # 参考: 《An Elegant Puzzle》1.1节 "4个原则确定团队规模"
    # =========================================================================

    # 经理:工程师 最佳比例 (1:6 到 1:8)
    TEAM_SIZING_MGR_ENG_MIN: int = 6
    TEAM_SIZING_MGR_ENG_MAX: int = 8
    # 高级经理:经理 最佳比例 (1:4 到 1:6)
    TEAM_SIZING_DIR_MGR_MIN: int = 4
    TEAM_SIZING_DIR_MGR_MAX: int = 6
    # 团队最小人数 (低于此数难以形成文化, 参考 1.1节 小团队可行性原则)
    TEAM_SIZING_MIN_TEAM_SIZE: int = 4
    # 值班轮值最少人数 (参考 1.1节 待命轮值原则)
    TEAM_SIZING_MIN_ONCALL_SIZE: int = 8

    # =========================================================================
    # 数学模型系数 — 综合健康分
    # 将所有模型输出加权聚合为 0-100 的管理仪表盘核心指标
    #
    # Health = w_dora·DORA_score + w_debt·(1-debt_interest)
    #        + w_hero·(1-gini) + w_state·state_score
    # =========================================================================

    HEALTH_W_DORA: float = 0.30      # DORA 四指标权重
    HEALTH_W_DEBT: float = 0.25      # 技术债权重 (取反后越低越健康)
    HEALTH_W_HERO: float = 0.20      # 英雄检测权重 (取反后越低越健康)
    HEALTH_W_STATE: float = 0.25     # 团队状态权重

    def model_post_init(self, __context: Any) -> None:
        """
        根据环境变量自动检测可用的 LLM 服务商, 并设置默认模型。

        优先级策略: 以 LLM_PROVIDER 声明的服务商优先, 同时检测其他已配置的服务商
        作为备选。这种设计确保即使主服务商不可用, 系统仍能降级运行。
        """
        # 服务商 → 可用性检测条件
        provider_checks: dict[Provider, Any] = {
            Provider.OLLAMA: self.OLLAMA_MODEL,
            Provider.ZHIPU: self.ZHIPU_API_KEY,
            Provider.OPENAI_COMPATIBLE: self.COMPATIBLE_BASE_URL and self.COMPATIBLE_MODEL,
            Provider.OPENAI: self.OPENAI_API_KEY,
            Provider.DEEPSEEK: self.DEEPSEEK_API_KEY,
            Provider.ANTHROPIC: self.ANTHROPIC_API_KEY,
        }

        active_providers = [p for p, check in provider_checks.items() if check]

        # 至少需要一个 LLM 服务商 (用于代码Review和任务分类)
        # 但允许无 LLM 运行纯指标计算模式
        if not active_providers:
            import logging
            logging.getLogger(__name__).warning(
                "未检测到任何 LLM API Key, 代码Review和任务分类功能将不可用。"
                "仅指标计算功能可正常使用。"
            )
            return

        # 注册每个活跃服务商的可用模型
        provider_to_models = {
            Provider.OPENAI: set(OpenAIModelName),
            Provider.DEEPSEEK: set(DeepseekModelName),
            Provider.ANTHROPIC: set(AnthropicModelName),
            Provider.ZHIPU: set(ZhipuModelName),
            Provider.OLLAMA: set(OllamaModelName),
            Provider.OPENAI_COMPATIBLE: set(OpenAICompatibleName),
        }

        provider_defaults = {
            Provider.OPENAI: OpenAIModelName.GPT_4O_MINI,
            Provider.DEEPSEEK: DeepseekModelName.DEEPSEEK_CHAT,
            Provider.ANTHROPIC: AnthropicModelName.CLAUDE_HAIKU_35,
            Provider.ZHIPU: ZhipuModelName.GLM_4_FLASH,
            Provider.OLLAMA: OllamaModelName.OLLAMA_GENERIC,
            Provider.OPENAI_COMPATIBLE: OpenAICompatibleName.COMPATIBLE_DEFAULT,
        }

        for provider in active_providers:
            if provider in provider_to_models:
                self.AVAILABLE_MODELS.update(provider_to_models[provider])
                if self.DEFAULT_MODEL is None:
                    self.DEFAULT_MODEL = provider_defaults.get(provider)

    @property
    def gitlab_project_id_list(self) -> list[int]:
        """将逗号分隔的 GITLAB_PROJECT_IDS 解析为整数列表"""
        if not self.GITLAB_PROJECT_IDS:
            return []
        return [int(pid.strip()) for pid in self.GITLAB_PROJECT_IDS.split(",") if pid.strip()]

    @property
    def tech_debt_fix_keyword_list(self) -> list[str]:
        """将逗号分隔的关键词字符串解析为列表"""
        return [kw.strip().lower() for kw in self.TECH_DEBT_FIX_KEYWORDS.split(",") if kw.strip()]

    @property
    def author_alias_map(self) -> dict[str, str]:
        """
        解析 GITLAB_AUTHOR_ALIASES 为 别名->规范名 映射
        格式: "lwh14|刘文浩|lwh:刘文浩, uyplayer|热克甫:热克甫"
        """
        result: dict[str, str] = {}
        if not self.GITLAB_AUTHOR_ALIASES:
            return result
        for group in self.GITLAB_AUTHOR_ALIASES.split(","):
            group = group.strip()
            if ":" not in group:
                continue
            aliases_part, canonical = group.rsplit(":", 1)
            canonical = canonical.strip()
            for alias in aliases_part.split("|"):
                alias = alias.strip()
                if alias:
                    result[alias] = canonical
        return result


# 全局单例
settings = Settings()
