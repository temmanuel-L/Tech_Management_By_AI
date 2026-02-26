"""
LLM 客户端工厂 — 使用 LangChain 适配

设计模式参考: agent-service-toolkit-for-lobechat/src/core/llm.py
通过 get_model() 工厂函数, 根据模型枚举自动路由到对应的 LangChain Chat 模型。
"""

import logging
from functools import cache
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

from tech_mgmt_ai.config import settings
from tech_mgmt_ai.schema.models import (
    AllModelEnum,
    AnthropicModelName,
    DeepseekModelName,
    OllamaModelName,
    OpenAICompatibleName,
    OpenAIModelName,
    ZhipuModelName,
)

logger = logging.getLogger(__name__)


@cache
def get_model(model_name: AllModelEnum | None = None) -> BaseChatModel:
    """
    根据模型枚举获取对应的 LangChain Chat 模型实例。

    使用 @cache 确保相同模型配置只创建一次实例。
    """
    if model_name is None:
        model_name = settings.DEFAULT_MODEL
    if model_name is None:
        raise ValueError(
            "未配置默认 LLM 模型。请在 .env 中设置 LLM_PROVIDER 及对应的 API Key。"
        )

    # ---- OpenAI ----
    if isinstance(model_name, OpenAIModelName):
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise ValueError("使用 OpenAI 模型需要设置 OPENAI_API_KEY")
        return ChatOpenAI(
            model=model_name.value,
            openai_api_key=api_key.get_secret_value(),
            base_url=settings.OPENAI_BASE_URL,
        )

    # ---- Deepseek ----
    if isinstance(model_name, DeepseekModelName):
        api_key = settings.DEEPSEEK_API_KEY
        if not api_key:
            raise ValueError("使用 Deepseek 模型需要设置 DEEPSEEK_API_KEY")
        return ChatOpenAI(
            model=model_name.value,
            openai_api_key=api_key.get_secret_value(),
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    # ---- Anthropic ----
    if isinstance(model_name, AnthropicModelName):
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("使用 Anthropic 模型需要设置 ANTHROPIC_API_KEY")
        return ChatAnthropic(
            model=model_name.value,
            anthropic_api_key=api_key.get_secret_value(),
        )

    # ---- 智谱 GLM ----
    if isinstance(model_name, ZhipuModelName):
        api_key = settings.ZHIPU_API_KEY
        if not api_key:
            raise ValueError("使用智谱 GLM 模型需要设置 ZHIPU_API_KEY")
        # 智谱目前通过 OpenAI 兼容层使用
        return ChatOpenAI(
            model=model_name.value,
            openai_api_key=api_key.get_secret_value(),
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        )

    # ---- Ollama (本地) ----
    if isinstance(model_name, OllamaModelName):
        base_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}"
        actual_model = settings.OLLAMA_MODEL or model_name.value
        return ChatOllama(
            model=actual_model,
            base_url=base_url,
        )

    # ---- OpenAI Compatible (通用兼容接口) ----
    if isinstance(model_name, OpenAICompatibleName):
        api_key = settings.COMPATIBLE_API_KEY
        base_url = settings.COMPATIBLE_BASE_URL
        if not base_url:
            raise ValueError("使用 OpenAI 兼容接口需要设置 COMPATIBLE_BASE_URL")
        actual_model = settings.COMPATIBLE_MODEL or model_name.value
        return ChatOpenAI(
            model=actual_model,
            openai_api_key=api_key.get_secret_value() if api_key else "no-key",
            base_url=base_url,
        )

    raise ValueError(f"未知的模型类型: {model_name}")


def chat_completion(
    prompt: str,
    system_prompt: str = "",
    model_name: AllModelEnum | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """
    便捷的单轮对话函数, 封装 LangChain 调用。

    Args:
        prompt: 用户消息内容
        system_prompt: 系统提示词
        model_name: 指定模型
        temperature: 生成温度
        max_tokens: 最大生成 token 数

    Returns:
        LLM 生成的文本内容
    """
    model = get_model(model_name)
    
    # LangChain 模型参数通常在初始化或 invoke 时设置
    # 此处为简单起见, 假设 get_model 返回的模型已基本配置好, 
    # 或者我们在此处进行临时覆盖 (但某些供应商不支持 bind 参数动态修改所有项)
    
    messages = []
    if system_prompt:
        messages.append(("system", system_prompt))
    messages.append(("user", prompt))

    model_name = getattr(model, "model_name", "unknown")
    logger.info("LLM chat_completion 调用: model=%s, prompt_len=%d, system_len=%d", model_name, len(prompt), len(system_prompt))

    # 绑定参数
    chain = model.bind(temperature=temperature, max_tokens=max_tokens)
    response = chain.invoke(messages)

    content = str(response.content) or ""
    logger.info("LLM chat_completion 响应: len=%d, preview=%s", len(content), content[:100] if content else "")
    return content
