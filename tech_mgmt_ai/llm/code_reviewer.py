"""
LLM 代码审查模块

基于 LangChain bind_tools 实现结构化输出, 避免手动解析 JSON 的不稳定性。
映射《An Elegant Puzzle》2.6节: 技术债识别与代码质量评估。
"""

import logging
from typing import List
from pydantic import BaseModel, Field

from tech_mgmt_ai.llm import get_model

logger = logging.getLogger(__name__)

# 代码Review的系统提示词
CODE_REVIEW_SYSTEM_PROMPT = """你是一位资深的代码审查专家。请审查以下代码 Diff, 并调用 CodeReviewResult 工具返回审查结果。

评估维度:
1. quality_score (1-10): 代码整体质量评分
2. issues: 发现的问题列表
3. is_paying_debt: 该变更是否在偿还技术债 (重构、修复、清理)
4. is_creating_debt: 该变更是否可能引入新的技术债
5. summary: 一句话总结 (中文)
"""


class CodeReviewIssue(BaseModel):
    """代码审查发现的单个问题"""
    category: str = Field(..., description="问题类别 (security / architecture / maintainability / testing / performance)")
    severity: str = Field(..., description="严重程度 (critical / major / minor / suggestion)")
    description: str = Field(..., description="问题描述 (中文)")
    line_hint: str = Field("", description="涉及的代码位置提示")


class CodeReviewResult(BaseModel):
    """
    LLM 代码审查结果 (用于 bind_tools 结构化输出)
    """
    quality_score: int = Field(5, ge=1, le=10, description="代码质量评分 (1-10)")
    issues: List[CodeReviewIssue] = Field(default_factory=list, description="发现的问题列表")
    is_paying_debt: bool = Field(False, description="是否在偿还技术债")
    is_creating_debt: bool = Field(False, description="是否在引入新技术债")
    summary: str = Field("", description="一句话总结")


def review_code_diff(
    diff: str,
    mr_title: str = "",
    max_diff_chars: int = 8000,
) -> CodeReviewResult:
    """
    对 Merge Request 的 Diff 进行 LLM 代码审查
    """
    if not diff.strip():
        return CodeReviewResult(summary="空 Diff, 无需审查")

    # 截断过长的 Diff
    truncated = diff[:max_diff_chars]
    if len(diff) > max_diff_chars:
        truncated += "\n\n... (Diff 已截断, 仅展示前 " + str(max_diff_chars) + " 字符)"

    prompt = f"MR 标题: {mr_title}\n\n代码 Diff:\n```\n{truncated}\n```"

    try:
        logger.info("LLM 代码Review 开始: diff_len=%d, mr_title=%s", len(diff), mr_title[:50] if mr_title else "")
        model = get_model()
        llm_with_tools = model.bind_tools([CodeReviewResult])
        messages = [
            ("system", CODE_REVIEW_SYSTEM_PROMPT),
            ("user", prompt),
        ]
        response = llm_with_tools.invoke(messages)

        # 解析 tool_calls (LangChain 可能使用 "CodeReviewResult" 或 "code_review_result")
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            name = tool_call.get("name", "")
            if "CodeReviewResult" in name or "code_review_result" in name:
                args = tool_call.get("args", {})
                # 处理 issues 可能为 dict 列表
                issues_raw = args.get("issues", [])
                issues = []
                for i in issues_raw:
                    if isinstance(i, dict):
                        issues.append(CodeReviewIssue(**i))
                    else:
                        issues.append(CodeReviewIssue(category="", severity="", description=str(i)))
                return CodeReviewResult(
                    quality_score=args.get("quality_score", 5),
                    issues=issues,
                    is_paying_debt=args.get("is_paying_debt", False),
                    is_creating_debt=args.get("is_creating_debt", False),
                    summary=args.get("summary", ""),
                )

        logger.warning(f"LLM 未返回结构化 tool_calls, 降级为默认结果。content={str(response.content)[:200]}")
        return CodeReviewResult(summary="模型未返回结构化结果")

    except Exception as e:
        logger.error(f"LLM 代码Review失败: {e}")
        return CodeReviewResult(summary=f"LLM 调用失败: {e}")
