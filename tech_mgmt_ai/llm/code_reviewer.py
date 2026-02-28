"""
LLM 代码审查模块

基于 LangChain bind_tools 实现结构化输出, 避免手动解析 JSON 的不稳定性。
映射《An Elegant Puzzle》2.6节: 技术债识别与代码质量评估。

支持同步 invoke 与异步 ainvoke, 便于并发调用以缩短总耗时。
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
3. is_paying_debt: 该变更是否在偿还技术债 (修复bug、重构优化、清理冗余、改进架构)
4. is_paying_debt_reason: 如果 is_paying_debt 为 true，说明该变更为何属于偿债类别（如修复了哪类问题、做了何种重构等，简洁中文，50字以内）
5. is_creating_debt: 该变更是否可能引入新的技术债 (硬编码、重复代码、缺乏注释等)
6. is_creating_debt_reason: 如果 is_creating_debt 为 true，说明引入了哪些技术债（仅文字原因，简洁中文，50字以内）
7. is_creating_debt_code_block: 若 is_creating_debt 为 true 且可定位到具体问题代码，用纯 Markdown 填写：以「**问题代码**」为标题换行后，用 ``` 代码块包裹问题代码并保持缩进；无法定位时留空
8. is_creating_debt_correct_action: 如果 is_creating_debt 为 true，给出改进建议（50字以内）
9. is_adding_new_function: 该变更是否为新增业务功能（feat 类型的新功能开发）
10. is_adding_new_function_reason: 如果 is_adding_new_function 为 true，说明该变更为何属于新业务/新功能类别（简洁中文，50字以内）
11. summary: 一句话总结 (中文)
"""


def _build_review_prompt(
    diff: str,
    title: str = "",
    author_comment: str = "",
    max_diff_chars: int = 8000,
) -> str:
    """构建 LLM 审查的 prompt, 将标题、作者评论与 diff 合并"""
    truncated = diff[:max_diff_chars]
    if len(diff) > max_diff_chars:
        truncated += "\n\n... (Diff 已截断, 仅展示前 " + str(max_diff_chars) + " 字符)"

    parts = []
    if title:
        parts.append(f"标题: {title}")
    if author_comment and author_comment.strip():
        parts.append(f"作者说明/评论:\n{author_comment.strip()}")
    parts.append(f"代码 Diff:\n```\n{truncated}\n```")
    return "\n\n".join(parts)


def _parse_tool_call_response(response) -> "CodeReviewResult":
    """从 LLM 响应解析 CodeReviewResult"""
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        name = tool_call.get("name", "")
        if "CodeReviewResult" in name or "code_review_result" in name:
            args = tool_call.get("args", {})
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
                is_paying_debt_reason=args.get("is_paying_debt_reason", ""),
                is_creating_debt=args.get("is_creating_debt", False),
                is_creating_debt_reason=args.get("is_creating_debt_reason", ""),
                is_creating_debt_code_block=args.get("is_creating_debt_code_block", ""),
                is_creating_debt_correct_action=args.get("is_creating_debt_correct_action", ""),
                is_adding_new_function=args.get("is_adding_new_function", False),
                is_adding_new_function_reason=args.get("is_adding_new_function_reason", ""),
                summary=args.get("summary", ""),
            )
    logger.warning(f"LLM 未返回结构化 tool_calls, 降级为默认结果。content={str(response.content)[:200]}")
    return CodeReviewResult(summary="模型未返回结构化结果")


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
    quality_score: int = Field(5, ge=1, le=10, description="代码整体质量评分，1=极差，5=一般，10=优秀")
    issues: List[CodeReviewIssue] = Field(default_factory=list, description="发现的问题列表")
    is_paying_debt: bool = Field(
        False,
        description="是否在偿还旧技术债：修复bug、重构优化、清理冗余、改进架构、消除警告等正向改进"
    )
    is_paying_debt_reason: str = Field(
        "",
        description="如果 is_paying_debt 为 true，说明该变更为何属于偿债类别（如修复了哪类问题、做了何种重构等，简洁中文原因说明，50字以内）"
    )
    is_creating_debt: bool = Field(
        False,
        description="是否在引入新技术债：硬编码、重复代码、缺乏注释、命名不规范、引入安全风险、遗留待办等"
    )
    is_creating_debt_reason: str = Field(
        "",
        description="如果 is_creating_debt 为 true，说明引入了哪些技术债（仅文字原因，简洁中文，50字以内；不要在此字段中放代码）"
    )
    is_creating_debt_code_block: str = Field(
        "",
        description="若 is_creating_debt 为 true 且可定位到具体问题代码，用纯 Markdown 填写：以「**问题代码**」为标题换行后，用 ``` 代码块包裹问题代码并保持缩进便于阅读；无法定位时留空"
    )
    is_creating_debt_correct_action: str = Field(
        "",
        description="如果 is_creating_debt 为 true，给出改进建议（简洁的中文建议，50字以内）"
    )
    is_adding_new_function: bool = Field(
        False,
        description="是否在新增业务功能（feat 类型的新功能开发，不包含修复、重构等）"
    )
    is_adding_new_function_reason: str = Field(
        "",
        description="如果 is_adding_new_function 为 true，说明该变更为何属于新业务/新功能类别（简洁的中文原因说明，50字以内）"
    )
    summary: str = Field("", description="一句话总结 (中文)")


def review_code_diff(
    diff: str,
    mr_title: str = "",
    author_comment: str = "",
    max_diff_chars: int = 8000,
) -> CodeReviewResult:
    """
    对 Merge Request 或 Commit 的 Diff 进行 LLM 代码审查 (同步版本)
    author_comment: 作者说明 (MR 的 description 或 Commit 的 message), 与 diff 一并推给 LLM
    """
    if not diff.strip():
        return CodeReviewResult(summary="空 Diff, 无需审查")

    prompt = _build_review_prompt(diff, title=mr_title, author_comment=author_comment, max_diff_chars=max_diff_chars)

    try:
        logger.info("LLM 代码Review 开始: diff_len=%d, title=%s", len(diff), (mr_title or "")[:50])
        model = get_model()
        llm_with_tools = model.bind_tools([CodeReviewResult])
        messages = [
            ("system", CODE_REVIEW_SYSTEM_PROMPT),
            ("user", prompt),
        ]
        response = llm_with_tools.invoke(messages)
        return _parse_tool_call_response(response)
    except Exception as e:
        logger.error(f"LLM 代码Review失败: {e}")
        return CodeReviewResult(summary=f"LLM 调用失败: {e}")


async def areview_code_diff(
    diff: str,
    mr_title: str = "",
    author_comment: str = "",
    max_diff_chars: int = 8000,
) -> CodeReviewResult:
    """
    对 Merge Request 或 Commit 的 Diff 进行 LLM 代码审查 (异步版本, 用于并发)
    author_comment: 作者说明 (MR 的 description 或 Commit 的 message), 与 diff 一并推给 LLM
    """
    if not diff.strip():
        return CodeReviewResult(summary="空 Diff, 无需审查")

    prompt = _build_review_prompt(diff, title=mr_title, author_comment=author_comment, max_diff_chars=max_diff_chars)

    try:
        logger.info("LLM 代码Review 开始 (async): diff_len=%d, title=%s", len(diff), (mr_title or "")[:50])
        model = get_model()
        llm_with_tools = model.bind_tools([CodeReviewResult])
        messages = [
            ("system", CODE_REVIEW_SYSTEM_PROMPT),
            ("user", prompt),
        ]
        response = await llm_with_tools.ainvoke(messages)
        return _parse_tool_call_response(response)
    except Exception as e:
        logger.error(f"LLM 代码Review失败: {e}")
        return CodeReviewResult(summary=f"LLM 调用失败: {e}")
