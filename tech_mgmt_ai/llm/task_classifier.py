import logging
from pydantic import BaseModel, Field
from typing import Literal

from tech_mgmt_ai.llm import get_model

logger = logging.getLogger(__name__)

# 任务类型的字面量
TaskType = Literal["feature", "fix", "debt", "ops"]

class TaskClassification(BaseModel):
    """任务分类结果"""
    category: TaskType = Field(..., description="任务类别: feature(新功能), fix(Bug修复), debt(技术债), ops(运维)")


# 任务分类的系统提示词
TASK_CLASSIFIER_SYSTEM_PROMPT = """你是一位技术项目管理专家。请根据任务标题和描述, 调用 TaskClassification 工具对任务进行分类。

分类标准:
- feature: 新功能开发、需求实现、用户故事
- fix: Bug 修复、错误修复、问题处理
- debt: 技术债偿还、代码重构、架构优化、依赖升级、文档补全
- ops: 运维工作、基础设施、CI/CD、监控、部署配置
"""


def classify_task(title: str, description: str = "") -> str:
    """
    通过 LLM 对任务进行语义分类
    """
    prompt = f"任务标题: {title}"
    if description:
        # 截断描述
        prompt += f"\n任务描述: {description[:500]}"

    try:
        logger.info("LLM 任务分类 开始: title=%s", title[:80] if title else "")
        model = get_model()
        llm_with_tools = model.bind_tools([TaskClassification])
        
        messages = [
            ("system", TASK_CLASSIFIER_SYSTEM_PROMPT),
            ("user", prompt)
        ]
        
        response = llm_with_tools.invoke(messages)
        
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            name = tool_call.get("name", "")
            if "TaskClassification" in name or "task_classification" in name:
                return tool_call.get("args", {}).get("category", "feature")

        # 降级处理
        logger.warning(f"LLM 未能分类任务, 使用关键词匹配。内容: {response.content}")
        return _keyword_fallback(title, description)

    except Exception as e:
        logger.error(f"LLM 任务分类失败: {e}, 回退为关键词匹配")
        return _keyword_fallback(title, description)


def _keyword_fallback(title: str, description: str = "") -> str:
    """
    关键词回退分类 (当 LLM 不可用时)
    """
    text = f"{title} {description}".lower()

    fix_keywords = ["fix", "bug", "修复", "修改", "问题", "error", "crash", "hotfix"]
    debt_keywords = ["refactor", "重构", "优化", "清理", "迁移", "upgrade", "tech debt", "技术债"]
    ops_keywords = ["部署", "运维", "监控", "ci/cd", "pipeline", "infra", "docker", "k8s"]

    if any(kw in text for kw in fix_keywords):
        return "fix"
    elif any(kw in text for kw in debt_keywords):
        return "debt"
    elif any(kw in text for kw in ops_keywords):
        return "ops"
    else:
        return "feature"
