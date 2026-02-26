# AI 技术管理工具 (tech_mgmt_ai)

基于《An Elegant Puzzle》(工程管理的要素) 一书，为中高层技术管理者提供数据驱动的管理决策支持。

## 架构概览

```
感知层 (Sensors)          认知层 (Cognition)       逻辑层 (Logic)            执行层 (Actuators)
┌──────────────┐         ┌──────────────┐        ┌──────────────┐         ┌──────────────┐
│ GitLab API   │───────▶│ LLM 代码Review│──────▶│ 技术债利息率  │──────▶│ 综合健康分    │
│ (MR/Commit)  │        │ LLM 任务分类  │       │ DORA 四指标   │        │ 告警规则引擎  │
│              │        │              │        │ 团队状态诊断  │        │ 飞书/钉钉通知  │
│ 飞书 API     │        │              │        │ 英雄检测      │        │ Vue 管理看板  │
│ (Tasks/Bugs) │        │              │        │ 团队规模校准  │        │              │
└──────────────┘        └──────────────┘        └──────────────┘        └──────────────┘
```

## 核心模型与书籍映射

| 模块 | 书中章节 | 数学模型 |
|---|---|---|
| 团队四状态 | 1.2节 | 多维加权评分 S = w₁·backlog + w₂·debt + w₃·morale + w₄·innovation |
| 团队规模 | 1.1节 | 经理:工程师 = 1:6~8, 高级经理:经理 = 1:4~6 |
| 技术债 | 2.5/2.6节 | 利息率 I = fix_changes / total_changes |
| DORA 指标 | 2.1节 | Lead Time, Deploy Freq, CFR, MTTR (4级分类) |
| 英雄检测 | 4.6节 | 基尼系数 (代码提交集中度) |
| 综合健康分 | 附录 | 加权聚合: 0-100 分 |

## 快速开始 (Docker)

```bash
# 1. 复制配置文件 (必须, docker-compose 依赖 .env 注入环境变量)
cp .env.example .env
# 编辑 .env 填入 LLM API Key (可选) 和 GitLab Token (可选)
# 使用 mock 数据源时可不配置 GitLab, 直接运行分析即可

# 2. 一键启动全部服务
docker compose up -d --build

# 3. 开发模式 (代码变更自动同步/重启)
docker compose watch

# 4. 访问
#   前端看板: http://localhost:3000
#   后端 API: http://localhost:8000/docs (Swagger UI)
```

> **注意**: 若 `.env` 不存在, docker-compose 会因 `env_file: .env` 报错。请务必先执行 `cp .env.example .env`。

### Docker 服务

| 服务 | 端口 | 说明 |
|---|---|---|
| frontend | 3000 | Vue 3 管理看板 (nginx) |
| backend | 8000 | FastAPI REST API |
| postgres | 5432 | PostgreSQL 指标存储 |

### 数据库: SQLite 与 PostgreSQL

- **Docker 部署**: 使用 PostgreSQL (由 docker-compose 注入 `DATABASE_URL`)
- **本地开发**: 未设置 `DATABASE_URL` 时自动回退到 SQLite (`tech_mgmt_ai.db`)
- 逻辑见 `tech_mgmt_ai/storage/database.py` 的 `get_database_url()`

## 本地开发

```bash
# 后端
pip install -e ".[dev]"
uvicorn tech_mgmt_ai.api.app:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev

# CLI 模式
python -m tech_mgmt_ai analyze
python -m tech_mgmt_ai team-sizing --engineers 24 --managers 3

# 测试
pytest tests/ -v
```

## 指标计算逻辑

| 指标 | 数据来源 | 计算公式 |
|------|----------|----------|
| **技术债利息率** | Commits | `fix_changes / total_changes`（按代码行数）；无 stats 时用 `fix_count / total_count` 兜底 |
| **英雄检测 (基尼)** | Commits | 基尼系数衡量提交集中度，0=均匀，1=集中 |
| **DORA Lead Time** | 已合并 MR | `mean(merged_at - created_at)` |
| **DORA 部署频率** | Pipelines | `成功部署数 / 天数` |
| **DORA 变更失败率** | Pipelines | `失败部署数 / 总部署数` |
| **DORA MTTR** | Pipelines | 失败→成功的时间差均值 |
| **团队状态** | Issues + MR 评论 | 积压趋势、债务占比、士气(Review 参与)、创新占比 |

**说明**：Pipeline 需 Token 有 `read_api` 权限；项目 107 返回 403 时需检查 Token 权限。Issues 为 0 时团队状态各维度均为 0。

## 关于 LLM

当前分析流程 (`/api/analyze`) 使用**规则引擎**（关键词、Label 等），**不调用 LLM**。`code_reviewer` 与 `task_classifier` 模块已实现，可在后续接入 MR 代码 Review 或任务语义分类时使用，届时会输出 LLM 调用日志。

## 配置说明

所有配置通过 `.env` 文件管理，包括：
- **数据源**: GitLab URL/Token、飞书凭证
- **LLM 服务**: 基于 LangChain 构建，支持 OpenAI / Deepseek / 智谱 / Ollama / Anthropic。通过 Tool Binding 实现结构化的代码 Review 和任务分类。
- **模型系数**: 每个数学模型的权重和阈值，均可独立调整

详见 `.env.example` 中的注释说明。

