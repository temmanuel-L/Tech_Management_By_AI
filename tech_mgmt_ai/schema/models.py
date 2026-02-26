"""
LLM 服务商与模型枚举定义

设计模式参考: agent-service-toolkit-for-lobechat/src/schema/models.py
每个服务商有独立的 StrEnum, 通过 Provider 枚举统一标识。
AllModelEnum 为所有对话模型的联合类型, 用于类型安全的模型分发。
"""

from enum import StrEnum, auto
from typing import TypeAlias


class Provider(StrEnum):
    """
    LLM 服务商枚举

    用于标识当前活跃的 LLM 提供商, 在 Settings.model_post_init 中
    根据环境变量自动检测可用服务商。
    """
    OPENAI = auto()
    DEEPSEEK = auto()
    ANTHROPIC = auto()
    ZHIPU = auto()
    OLLAMA = auto()
    OPENAI_COMPATIBLE = auto()  # 兼容 OpenAI API 的第三方服务


class OpenAIModelName(StrEnum):
    """OpenAI 官方模型 https://platform.openai.com/docs/models"""
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_TURBO = "gpt-4-turbo"


class DeepseekModelName(StrEnum):
    """Deepseek 模型 https://api-docs.deepseek.com/quick_start/pricing"""
    DEEPSEEK_CHAT = "deepseek-chat"


class AnthropicModelName(StrEnum):
    """Anthropic Claude 模型 https://docs.anthropic.com/en/docs/about-claude/models"""
    CLAUDE_HAIKU_35 = "claude-3-5-haiku-latest"
    CLAUDE_SONNET_35 = "claude-3-5-sonnet-latest"


class ZhipuModelName(StrEnum):
    """
    智谱 GLM 系列
    https://docs.bigmodel.cn/cn/guide/start/model-overview
    对话补全: https://open.bigmodel.cn/api/paas/v4/chat/completions
    """
    GLM_4_FLASH = "glm-4-flash"        # 免费普惠模型, 适合大批量任务分类
    GLM_4_AIR = "glm-4-air"            # 高性价比, 适合代码Review
    GLM_4_PLUS = "glm-4-plus"          # 高性能, 适合复杂分析


class OllamaModelName(StrEnum):
    """本地 Ollama 模型 https://ollama.com/search"""
    OLLAMA_GENERIC = "qwen2.5:14b"     # 默认本地模型, 可通过 OLLAMA_MODEL 覆盖


class OpenAICompatibleName(StrEnum):
    """兼容 OpenAI API 格式的第三方服务"""
    COMPATIBLE_DEFAULT = "default"      # 占位, 实际模型名由 COMPATIBLE_MODEL 环境变量决定


# 所有对话 LLM 枚举的联合类型, 用于 get_model() 的类型标注
AllModelEnum: TypeAlias = (
    OpenAIModelName
    | DeepseekModelName
    | AnthropicModelName
    | ZhipuModelName
    | OllamaModelName
    | OpenAICompatibleName
)
