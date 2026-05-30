# PolicyAI

AI 经济政策分析工具包 — 多智能体报告生成、句级引用验证、多格式输出。

微服务架构，10 个模块，FastAPI + Python 3.12+。

## 项目文件速查

```
.
├── api-gateway/CLAUDE.md              # 统一入口：JWT/RBAC/限流/审计/反向代理
├── services/
│   ├── user-service/CLAUDE.md        # 认证、RBAC、LDAP/SSO、审计
│   ├── document-service/CLAUDE.md    # 文档解析（8 种格式+OCR）、双粒度切块
│   ├── kb-service/CLAUDE.md          # 混合搜索：向量+BM25→RRF→Reranker
│   ├── orchestration-service/CLAUDE.md # Agent 引擎：ReAct 循环、工具编排
│   ├── llm-router/CLAUDE.md          # 敏感度路由、本地/云端适配器
│   ├── citation-service/CLAUDE.md    # [ref:doc:page] 解析与验证
│   └── output-service/CLAUDE.md      # MD/DOCX(GB/T 9704)/XLSX/PPTX 生成
├── frontend/CLAUDE.md                 # React 19 + TypeScript + Ant Design
├── shared/CLAUDE.md                   # 共享基类、枚举、Pydantic 模型
├── celery/CLAUDE.md                   # 异步任务队列配置
├── db/CLAUDE.md                       # 11 张表 schema、迁移、种子数据
├── templates/CLAUDE.md                # Jinja2 提示词模板 + 输出样式
├── tests/CLAUDE.md                    # 纯 mock 测试，无外部依赖
├── milvus/CLAUDE.md                   # 向量数据库配置
└── doc/                               # 需求、架构设计、任务分解文档
```

## 开发速查

```bash
source .venv/bin/activate                      # 激活虚拟环境
docker compose up -d                           # 启动基础设施
cd <service-dir> && uv run uvicorn app:app     # 手动启动单服务
cd <service-dir> && pytest && mypy . && ruff . # 质量门
```

## 核心设计原则

- **引用格式**：LLM 输出使用 `[ref:doc_id:page_range]`，citation-service 验证置信度（direct/fuzzy/uncertain）
- **双粒度切块**：段落级(~300 tokens) + 章节级(~2000 tokens)
- **Agent 循环**：ReAct 变体，最多 5 轮迭代
- **测试零依赖**：所有外部依赖 mock，离线可运行
- **GB/T 9704**：中文公文标准 .docx 输出

## 参考资料

根目录下的 `doc/` 包含需求（proposal.md）、高层设计（high-level-design.md）、详细设计（detailed-design.md）、任务分解（tasks/*.md）及开发协议（prompt.md）。
