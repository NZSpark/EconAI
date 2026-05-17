# EconAI 概要设计文档

> 版本：v1.0 | 日期：2026-05-17 | 基于需求文档 v2.0（终稿）

---

## 1. 设计概述

### 1.1 设计目标

基于需求文档确认的机构级 AI 分析工具包定位，概要设计遵循以下目标：

- **模块化**：各服务独立部署、独立演进，通过 API 通信
- **可配置**：知识源、LLM 路由、分析工作流均可配置
- **可审计**：全链路操作日志 + 逐句来源追溯
- **安全合规**：混合 LLM 部署 + 数据不出内网 + 等保二级 + GDPR

### 1.2 核心设计决策

| 决策项 | 选择 | 简述 |
|--------|------|------|
| Embedding 模型 | text2vec / m3e | 中文开源 embedding，私有化部署 |
| 工作流编排 | 自研轻量 Agent | LLM 驱动工具调用，非固定流水线 |
| 来源追溯 | inline 内联引用 | 生成时插入来源标记，输出时解析和格式化 |
| 文档分块 | 多粒度分块 | 段落级（精确检索）+ 章节级（上下文窗口） |
| 检索策略 | 混合检索 + Reranker | 向量语义 + BM25 关键词 + 重排序 |
| 交互模式 | 异步任务 + 进度轮询 | 长任务后台执行，前端轮询进度 |
| 对话模式 | 单次生成 | 提交→等待→拿到结果，不含多轮修改 |

---

## 2. 系统架构

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                        客户端层                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              React + TypeScript SPA                          │ │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────────────┐   │ │
│  │  │ 项目管理 │ │ 知识库  │ │ 分析任务  │ │ 输出/导出      │   │ │
│  │  │ 视图    │ │ 管理    │ │ 提交/监控 │ │ 预览/审核      │   │ │
│  │  └─────────┘ └─────────┘ └──────────┘ └────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                                    │
                            TLS 1.2+ (HTTPS)
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                        API 网关层                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   FastAPI + Nginx                             │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │ │
│  │  │ 认证鉴权  │ │ 限流     │ │ RBAC     │ │ 审计日志       │  │ │
│  │  │ (JWT)    │ │ (token   │ │ 中间件   │ │ 中间件         │  │ │
│  │  │          │ │  bucket) │ │          │ │               │  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                        服务层                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ 文档解析  │ │ 知识库    │ │ 任务编排  │ │ 输出生成  │           │
│  │ Service  │ │ Service  │ │ Service  │ │ Service  │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────┐        │
│  │ 来源溯源  │ │ 用户权限  │ │     LLM 路由 Service     │        │
│  │ Service  │ │ Service  │ └──────────────────────────┘        │
│  └──────────┘ └──────────┘                                      │
└──────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                        数据与基础设施层                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │PostgreSQL│ │Milvus/   │ │  MinIO   │ │ Celery + Redis     │  │
│  │(业务数据) │ │Qdrant    │ │(文档存储) │ │ (异步任务队列)     │  │
│  │          │ │(向量索引) │ │          │ │                    │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────────────┐ │
│  │ 本地 LLM │ │ Claude   │ │ Prometheus + Grafana            │ │
│  │(vLLM/   │ │ API      │ │ (监控告警)                       │ │
│  │ Ollama) │ │ (云端)   │ │                                  │ │
│  └──────────┘ └──────────┘ └──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 模块划分与职责

```
EconAI
├── api-gateway/           # API 网关 + 中间件
│   ├── auth_middleware    # JWT 认证
│   ├── rbac_middleware    # 角色权限校验
│   ├── rate_limiter       # 频率限制
│   └── audit_middleware   # 操作审计
│
├── services/
│   ├── document-service/  # 文档解析服务
│   │   ├── ingestion      # 文件上传/导入
│   │   ├── parser         # 多格式解析器
│   │   ├── ocr            # OCR 处理 (Tesseract)
│   │   └── chunker        # 多粒度分块
│   │
│   ├── kb-service/        # 知识库服务
│   │   ├── project_kb     # 项目知识库 CRUD
│   │   ├── inst_kb        # 机构知识库 CRUD
│   │   ├── indexer        # 向量索引（embedding 生成 + 存储）
│   │   ├── searcher       # 混合检索（向量 + BM25 + Reranker）
│   │   └── lifecycle      # 归档、过期、删除
│   │
│   ├── orchestration-service/  # 任务编排服务
│   │   ├── task_manager   # 任务生命周期管理
│   │   ├── agent_engine   # 自研轻量 Agent 循环引擎
│   │   ├── tools          # Agent 可用工具（检索/生成/校验/格式化）
│   │   └── progress       # 进度追踪和报告
│   │
│   ├── llm-router/        # LLM 路由服务
│   │   ├── registry       # 模型注册表
│   │   ├── router         # 敏感度分析 + 路由决策
│   │   ├── adapter        # Claude API 适配器
│   │   ├── adapter        # vLLM/Ollama 本地适配器
│   │   └── tracker        # Token 使用量追踪
│   │
│   ├── output-service/    # 输出生成服务
│   │   ├── markdown_gen   # Markdown 生成
│   │   ├── docx_gen       # GB/T 9704 公文 .docx 生成
│   │   ├── xlsx_gen       # Excel 表格生成
│   │   ├── pptx_gen       # PPT 简报生成
│   │   └── template       # 格式模板管理
│   │
│   ├── citation-service/  # 来源溯源服务
│   │   ├── parser         # inline 引用解析器
│   │   ├── verifier       # 来源校验（匹配 chunk 元数据）
│   │   └── formatter      # 引用格式化（脚注/尾注/侧栏）
│   │
│   └── user-service/      # 用户权限服务
│       ├── user_mgmt      # 用户管理
│       ├── group_mgmt     # 项目组管理
│       ├── role_mgmt      # 角色管理
│       ├── ldap_auth      # LDAP/SSO 对接
│       └── audit_log      # 审计日志存储与查询
```

### 2.3 模块交互矩阵

```
                    ┌──────────┐
                    │  API GW  │
                    └────┬─────┘
                         │
         ┌───────────────┼───────────────┬───────────────┐
         ▼               ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐
    │ 文档服务  │    │ 知识库   │    │ 用户权限  │    │ 任务编排 │
    └────┬─────┘    │ 服务    │    │ 服务     │    │ 服务    │
         │          └────┬─────┘    └──────────┘    └────┬─────┘
         │               │                              │
         │  写入 MinIO    │  写入 Milvus/                │
         │               │  Qdrant                      │
         ▼               ▼                              │
    ┌─────────┐    ┌──────────┐                         │
    │  MinIO  │    │ 向量数据库│                          │
    └─────────┘    └──────────┘                         │
                                                        │
                          ┌─────────────────────────────┤
                          ▼               ▼             ▼
                     ┌─────────┐   ┌──────────┐  ┌──────────┐
                     │ LLM 路由│   │ 输出生成  │  │ 来源溯源  │
                     └────┬────┘   └──────────┘  └──────────┘
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
           ┌──────────┐    ┌──────────┐
           │Claude API│    │ 本地 LLM │
           │ (云端)   │    │ (GPU集群)│
           └──────────┘    └──────────┘
```

---

## 3. 核心模块设计

### 3.1 文档解析服务 (Document Service)

#### 3.1.1 职责

接收用户上传的文档，完成格式识别、内容提取、结构化分块，为后续索引和检索提供结构化数据。

#### 3.1.2 处理流水线

```
文件上传 → 格式识别 → 内容提取 → 元数据提取 → 多粒度分块 → 存储
               │           │            │
               ▼           ▼            ▼
           Tesseract   全文文本     标题/作者/日期
           (扫描件)    结构化信息    页码/章节
```

#### 3.1.3 格式处理器

| 格式 | 解析器 | 输出 |
|------|--------|------|
| PDF | PyMuPDF / pdfplumber | 全文文本 + 页码 + 表格 |
| Word | python-docx | 全文文本 + 段落样式 + 表格 |
| Markdown/纯文本 | 标准库 | 全文文本 |
| Excel/CSV | openpyxl / pandas | 结构化表格 + 列名语义 |
| PowerPoint | python-pptx | 逐页文本 |
| 图片 PDF/图片 | Tesseract OCR → 同 PDF | 全文文本 + 页码 |
| .eml | email 标准库 | 正文 + 元数据（发件人/日期/主题） |
| HTML/MHTML | BeautifulSoup | 正文提取 + 原始链接 |

#### 3.1.4 多粒度分块 (Chunker)

```
原始文档 (以 PDF 为例)
       │
       ├── 章节级 Chunk (∼2000 tokens)
       │   ├── 包含完整章节/小节
       │   ├── 元数据: {doc_id, section_title, page_range}
       │   └── 用途: Agent 生成时提供充足上下文
       │
       └── 段落级 Chunk (∼300 tokens)
           ├── 按自然段落分割
           ├── 元数据: {doc_id, section_title, page_number, paragraph_index}
           └── 用途: 精确检索 + inline 引用溯源
```

**分块参数**：
- 段落级：目标 300 token，最小 100，最大 500；按自然段落边界对齐
- 章节级：目标 2000 token，最小 500，最大 3000；按章节标题对齐
- 相邻 chunk 重叠：段落级 50 token，章节级 100 token

### 3.2 知识库服务 (KB Service)

#### 3.2.1 职责

管理知识库的生命周期，将分块后的文档内容转为向量索引，提供混合检索能力。

#### 3.2.2 索引流水线

```
Chunk → text2vec/m3e Embedding → 向量存入 Milvus/Qdrant
     → 文本 + 元数据 → 存入 PostgreSQL (document_chunks 表)
     → 文本 → BM25 索引 (Elasticsearch 或 PG 内置全文搜索)
```

#### 3.2.3 混合检索流程

```
用户查询 (自然语言)
       │
       ├──→ 向量检索 (Milvus/Qdrant)          → top_k=50
       │        语义相似度匹配
       │
       ├──→ BM25 关键词检索 (PostgreSQL FTS)   → top_k=50
       │        精确关键词匹配
       │
       └──→ 结果融合 (RRF: Reciprocal Rank Fusion)
             │
             ▼
           融合后 top_k=30
             │
             ▼
           Reranker (BGE-Reranker / cross-encoder)
             │  重排序，提升相关性
             ▼
           top_k=10 返回给 Agent
```

**RRF 融合公式**：
```
score(doc) = Σ 1/(k + rank_i(doc))
```
其中 k=60，rank_i 为在各检索器中的排名。

#### 3.2.4 知识库隔离

| 知识库类型 | 隔离方式 | 说明 |
|------------|----------|------|
| 项目知识库 | 按 project_id 过滤 | 仅本项目可见 |
| 机构知识库 | 按 group_id + 访问策略 | 组内共享，可跨组授权 |

查询时注入项目上下文过滤器，确保数据隔离。

### 3.3 任务编排服务 (Orchestration Service)

#### 3.3.1 自研轻量 Agent 设计

Agent 循环的核心是一个 **ReAct 模式**的变体——Plan → Retrieve → Generate → Verify → Decide：

```
┌─────────────────────────────────────────────┐
│              Agent 循环                      │
│                                             │
│  1. Plan                                    │
│     分析任务目标 → 确定信息缺口 → 生成检索计划 │
│     ↓                                       │
│  2. Retrieve (Tool)                         │
│     调用 KB Service 混合检索                 │
│     ↓                                       │
│  3. Generate (Tool)                         │
│     调用 LLM 生成带 inline 引用的内容片段      │
│     ↓                                       │
│  4. Verify  (Tool)                          │
│     校验 inline 引用是否匹配检索到的 chunk     │
│     ↓                                       │
│  5. Decide                                  │
│     - 信息充分？→ 进入 Format 阶段            │
│     - 信息不足？→ 回到 Plan (最多 5 轮迭代)    │
│     ↓                                       │
│  6. Format (Tool)                           │
│     整合片段 → 完整文档                       │
└─────────────────────────────────────────────┘
```

#### 3.3.2 Agent 工具定义

| 工具名 | 描述 | 输入 | 输出 |
|--------|------|------|------|
| `search_kb` | 混合检索知识库 | query, filters, top_k | 带元数据的 chunk 列表 |
| `generate_section` | LLM 生成章节内容 | system_prompt, context(chunks), section_goal | 带 inline 引用的文本 |
| `verify_citations` | 校验引用准确性 | generated_text, context_chunks | 校验报告（精确/模糊/无依据） |
| `extract_key_claims` | 提取关键论点 | generated_text | 结构化论点列表 |
| `compare_policies` | 多政策选项比较 | policy_descriptions, context | 对比分析文本 + 矩阵 |
| `format_output` | 格式化最终输出 | full_text, citations, format | 指定格式的文件 |

#### 3.3.3 Agent 提示词结构

```
System Prompt 组成:
  ├── 角色定义（"你是一个经济政策分析助手..."）
  ├── 当前任务描述
  ├── 知识源摘要（本次可用的文档清单）
  ├── 输出格式规范（含 inline 引用格式要求）
  ├── 可用工具说明
  └── 约束条件（置信度标记规则、不确定时标注"无证据支持"）
```

#### 3.3.4 任务状态机

```
pending ──→ running ──→ completed
                │
                ├──→ failed ──→ (可重试)
                │
                └──→ cancelled
```

#### 3.3.5 进度追踪

Agent 每个步骤完成后更新任务进度：

```python
# progress 字段结构
{
    "step": "retrieving",     # 当前步骤名
    "step_index": 2,          # 第几步
    "total_steps_estimate": 8, # 预估总步数
    "message": "正在检索相关政策文献..."  # 用户可读的进度描述
}
```

### 3.4 LLM 路由服务

#### 3.4.1 架构

```
调用方 (Agent/其他服务)
       │
       ▼
┌──────────────────┐
│   Sensitivity     │
│   Analyzer        │  分析请求中是否包含内部/敏感知识源
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   Router          │
│                   │
│  敏感数据? ──→ 本地 LLM (vLLM/Ollama)
│  公开数据? ──→ Claude API (云端)
│  用户指定? ──→ 用户选择的模型
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   Adapter         │  统一请求/响应格式
│                   │
│  ClaudeAdapter    │  Anthropic SDK
│  LocalAdapter     │  OpenAI-compatible API (vLLM/Ollama 均支持)
└──────────────────┘
```

#### 3.4.2 敏感度判定规则

```python
def analyze_sensitivity(task: AnalysisTask, kb_sources: list[KBSource]) -> Sensitivity:
    """判定分析任务的敏感度"""
    
    # 规则1：任务的知识源包含内部报告 → 敏感
    if any(source.source_type == "internal" for source in kb_sources):
        return Sensitivity.HIGH
    
    # 规则2：任务类型是政策草案撰写（通常基于内部文件） → 敏感
    if task.type == TaskType.POLICY_DRAFT:
        return Sensitivity.HIGH
    
    # 规则3：用户显式标记 → 尊重用户选择
    if task.sensitivity_override:
        return task.sensitivity_override
    
    # 规则4：纯公开文献分析 → 非敏感，走云端
    return Sensitivity.LOW
```

#### 3.4.3 统一请求格式

本地模型通过 vLLM/Ollama 的 OpenAI 兼容 API 暴露，因此使用统一格式：

```json
{
    "model": "claude-sonnet-4-6 | local:qwen3 | local:deepseek-v3",
    "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
    "temperature": 0.3,
    "max_tokens": 4096,
    "stream": false
}
```

### 3.5 来源溯源服务 (Citation Service)

#### 3.5.1 Inline 引用格式

LLM 生成时需遵循约定的引用格式：

```
近年来，数字贸易规则已成为全球贸易治理的核心议题[ref:doc_123:p45-48]。
多项研究表明数字服务税对中小企业的影响存在显著异质性[ref:doc_456:p12|doc_789:p33-35]。
```

**格式规范**：
- 单引用：`[ref:{doc_id}:{page_range}]`
- 多引用：`[ref:{doc_id}:{page}|{doc_id}:{page}]`
- 无依据声明：`[ref:uncertain]` — LLM 自身推理，告知读者此为模型推理

#### 3.5.2 处理流水线

```
LLM 输出文本 (含 [ref:...] 标记)
       │
       ▼
  CitationParser
       │  正则提取所有 [ref:xxx] 标记
       │  建立 "句子 → doc_id → page_range" 映射
       ▼
  CitationVerifier
       │  查询 doc_id + page_range 是否在检索到的 chunks 中
       │  标记置信度: direct(精确匹配) | fuzzy(段落匹配) | uncertain(无匹配)
       ▼
  CitationFormatter
       │  生成用户可读的引用格式
       │  前端交互数据（点击展示原文）
       │  .docx 脚注/尾注
```

#### 3.5.3 置信度标记

| 置信度 | 含义 | 触发条件 |
|--------|------|----------|
| `direct` | 直接引用 | chunk 元数据的 page_range 与引用完全匹配 |
| `fuzzy` | 段落匹配 | chunk 文本语义相似度 > 0.85，但页码不完全一致 |
| `uncertain` | 模型推理 | LLM 生成但无法在检索到的 chunks 中找到直接依据 |

### 3.6 输出生成服务

#### 3.6.1 支持格式与生成方式

| 格式 | 生成引擎 | 关键要求 |
|------|----------|----------|
| Markdown | jinja2 模板渲染 | 纯文本 + 引用链接 |
| .docx | python-docx + 自定义模板 | GB/T 9704 公文国标（版头/主体/版记） |
| .xlsx | openpyxl | 对比矩阵、数据摘要 |
| .pptx | python-pptx | 关键发现简报，图表支持 |

#### 3.6.2 GB/T 9704 .docx 格式映射

```
公文要素              python-docx 实现
─────────────────────────────────────
版头 (发文机关标志)    → 页眉固定样式
发文字号              → 段落样式 "发文字号"
签发人                → 右对齐签名行
标题                  → 二号小标宋体，居中
主送机关              → 段落样式 "主送"
正文                  → 三号仿宋体，首行缩进2字符
附件说明              → 段落样式 "附件"
发文机关署名          → 右对齐，日期下对齐
成文日期              → 中文日期格式
版记 (抄送/印发)      → 页脚区域
```

#### 3.6.3 引用在导出文件中的呈现

- **.docx**：正文中以角标 [1],[2] 标注，文档末尾附引用清单，或页脚注形式
- **.md**：正文中保留 [ref:...] → 渲染为 `[^1]` 脚注语法
- **.xlsx**：单独 sheet "引用清单" 列出所有引用
- **.pptx**：每页底部小字标注引用源，最后一页放完整引用清单

---

## 4. 数据流

### 4.1 文献综述 — 完整数据流

```
时间线 →

[用户]                     [系统]
  │                         │
  ├─ 创建项目                │
  │                         ├─ 创建 project 记录
  │                         │
  ├─ 上传文献(多篇PDF)       │
  │                         ├─ 原始文件 → MinIO
  │                         ├─ 格式解析 → 文本提取
  │                         ├─ 多粒度分块 → chunks
  │                         ├─ 向量化(embedding) → Milvus/Qdrant
  │                         ├─ BM25 索引 → PostgreSQL FTS
  │                         └─ 元数据存储 → PostgreSQL
  │                         │
  ├─ 提交"文献综述"任务       │
  │  参数:                   │
  │  - 知识库范围(刚上传的文献) │
  │  - 综述主题/角度          │
  │  - 输出格式(.docx)        │
  │                         ├─ 创建 task 记录 (status=pending)
  │                         ├─ 推入 Celery 队列
  │                         │
  ├─ 轮询 GET /tasks/{id}/status
  │                         ├─ Agent 循环启动:
  │                         │   ┌─ Plan: "先检索所有文献的核心论点"
  │                         │   ├─ search_kb("数字贸易规则演变 核心论点")
  │                         │   ├─ generate_section(检索结果 → "研究背景"节)
  │                         │   ├─ verify_citations(生成文本)
  │                         │   ├─ Plan: "补充检索各文献的方法论差异"
  │                         │   ├─ search_kb("政策影响评估方法 实证分析")
  │                         │   ├─ generate_section(检索结果 → "方法论比较"节)
  │                         │   ├─ ...
  │                         │   └─ format_output(全文章节 → .docx)
  │                         │
  │                         ├─ 存储 task_outputs
  │                         ├─ 存储 citations
  │                         └─ status=completed
  │                         │
  ├─ 查看输出(Web预览)       │
  ├─ 点击引用标记查看来源     │
  ├─ 导出 .docx              │
  └─ 下载                    └─ 返回文件流
```

### 4.2 Agent 循环内部数据流

```
┌─────────────────────────────────────────────────────────┐
│                  Agent Engine                           │
│                                                        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐         │
│  │ Context  │───→│ LLM Call │───→│ Tool Call│         │
│  │ Builder  │    │ (Plan/   │    │ Execution│         │
│  │          │    │  Decide) │    │          │         │
│  └──────────┘    └──────────┘    └──────────┘         │
│       ▲                               │                │
│       │        ┌──────────┐          │                │
│       └────────│ State    │←─────────┘                │
│                │ Update   │                            │
│                └──────────┘                            │
│                                                        │
│  Agent State:                                          │
│  {                                                     │
│    "messages": [...],         // 对话历史               │
│    "retrieved_chunks": [...],  // 已检索的所有 chunk     │
│    "generated_sections": [...], // 已生成的章节          │
│    "citations": {...},        // 引用映射表             │
│    "plan": "...",             // 当前计划               │
│    "iteration": 3,            // 当前迭代轮次            │
│    "remaining_sections": [...] // 待完成章节            │
│  }                                                     │
└─────────────────────────────────────────────────────────┘
```

---

## 5. API 设计

### 5.1 RESTful API 端点

#### 5.1.1 认证

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户名密码登录 / LDAP 认证，返回 JWT |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 获取当前用户信息 |

#### 5.1.2 项目管理

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects` | 列出当前用户可见项目（受项目组隔离） |
| GET | `/api/projects/{id}` | 获取项目详情 |
| PUT | `/api/projects/{id}` | 更新项目信息 |
| DELETE | `/api/projects/{id}` | 删除项目（软删除，归档） |

#### 5.1.3 知识库

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/projects/{id}/documents` | 上传文档（multipart/form-data） |
| GET | `/api/projects/{id}/documents` | 列出项目文档 |
| GET | `/api/projects/{id}/documents/{doc_id}` | 获取文档详情和解析状态 |
| DELETE | `/api/projects/{id}/documents/{doc_id}` | 删除文档和索引 |
| POST | `/api/projects/{id}/documents/{doc_id}/reindex` | 重新索引文档 |
| POST | `/api/projects/{id}/search` | 搜索项目知识库 |
| POST | `/api/institutional/search` | 搜索机构知识库 |

#### 5.1.4 分析任务

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/projects/{id}/tasks` | 创建分析任务 |
| GET | `/api/projects/{id}/tasks` | 列出项目任务 |
| GET | `/api/tasks/{task_id}` | 获取任务详情 |
| GET | `/api/tasks/{task_id}/status` | 轮询任务状态和进度 |
| POST | `/api/tasks/{task_id}/cancel` | 取消任务 |
| POST | `/api/tasks/{task_id}/retry` | 重试失败任务 |

**创建任务请求体**：

```json
{
    "type": "literature_review",
    "title": "数字贸易规则对发展中国家的影响综述",
    "description": "综述近年关于数字贸易规则对发展中国家经济影响的学术文献和政策报告",
    "kb_sources": {
        "documents": ["doc_001", "doc_002", "doc_003"],
        "include_institutional": false
    },
    "output_formats": ["docx", "md"],
    "llm_preference": "auto",
    "analysis_params": {
        "focus_areas": ["经济影响", "政策建议", "实施挑战"],
        "comparison_dimensions": [],
        "methodology_quality": true
    }
}
```

#### 5.1.5 输出与导出

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/tasks/{task_id}/output` | 获取输出内容（Markdown 格式预览） |
| GET | `/api/tasks/{task_id}/output/citations` | 获取所有引用详情 |
| GET | `/api/tasks/{task_id}/output/citations/{citation_id}` | 获取单个引用详情（含原文摘录） |
| GET | `/api/tasks/{task_id}/export` | 导出文件（query: format=docx|md|xlsx|pptx） |

#### 5.1.6 管理端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/admin/users` | 创建用户 |
| GET | `/api/admin/users` | 列出用户 |
| PUT | `/api/admin/users/{id}` | 更新用户 |
| DELETE | `/api/admin/users/{id}` | 删除用户 |
| POST | `/api/admin/groups` | 创建项目组 |
| GET | `/api/admin/groups` | 列出项目组 |
| POST | `/api/admin/groups/{id}/members` | 添加组成员 |
| DELETE | `/api/admin/groups/{id}/members/{user_id}` | 移除组成员 |
| GET | `/api/admin/audit-logs` | 查询审计日志 |

### 5.2 错误响应格式

```json
{
    "error": {
        "code": "DOCUMENT_PARSE_FAILED",
        "message": "文档解析失败：PDF 第 3 页包含无法识别的编码",
        "details": {
            "document_id": "doc_123",
            "page": 3
        }
    }
}
```

### 5.3 分页与过滤

列表接口统一支持：

```
GET /api/projects?page=1&page_size=20&status=active&sort=created_at:desc
```

---

## 6. 数据模型

### 6.1 核心实体关系

```
┌──────────┐     ┌──────────────────┐     ┌──────────┐
│   User   │────→│ ProjectGroupMember│←────│ Project  │
│          │     │                  │     │  Group   │
└──────────┘     └──────────────────┘     └──────────┘
     │                                          │
     │ belongs_to                               │ has_many
     ▼                                          ▼
┌──────────┐     ┌──────────┐     ┌──────────────────┐
│  Project │────→│ Document │────→│  DocumentChunk   │
│          │     │          │     │                  │
└──────────┘     └──────────┘     └──────────────────┘
     │                                          │
     │ has_many                                 │ references
     ▼                                          ▼
┌──────────────┐                          ┌──────────┐
│ AnalysisTask │                          │ Citation │
│              │                          │          │
└──────────────┘                          └──────────┘
     │
     │ has_many
     ▼
┌──────────────┐
│ TaskOutput   │
│              │
└──────────────┘
```

### 6.2 关键表结构

#### users

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(255),
    display_name VARCHAR(128),
    role VARCHAR(32) NOT NULL DEFAULT 'analyst',  -- analyst | senior_researcher | project_admin | system_admin
    auth_provider VARCHAR(32) DEFAULT 'local',     -- local | ldap | sso
    ldap_dn VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

#### project_groups

```sql
CREATE TABLE project_groups (
    id UUID PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT now()
);
```

#### project_group_members

```sql
CREATE TABLE project_group_members (
    id UUID PRIMARY KEY,
    group_id UUID REFERENCES project_groups(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,  -- analyst | senior_researcher | project_admin
    UNIQUE(group_id, user_id)
);
```

#### projects

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    description TEXT,
    group_id UUID REFERENCES project_groups(id),
    created_by UUID REFERENCES users(id),
    status VARCHAR(32) DEFAULT 'active',  -- active | archived
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

#### documents

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    filename VARCHAR(512) NOT NULL,
    original_name VARCHAR(512) NOT NULL,
    format VARCHAR(32) NOT NULL,       -- pdf | docx | txt | md | xlsx | csv | pptx | eml | html | image
    size_bytes BIGINT,
    page_count INT,
    storage_path VARCHAR(1024),        -- MinIO 对象路径
    parse_status VARCHAR(32) DEFAULT 'pending',  -- pending | parsing | ready | error
    parse_error TEXT,
    metadata JSONB,                    -- {title, authors, date, source, ...}
    is_internal BOOLEAN DEFAULT false, -- 是否内部文档（影响LLM路由）
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_documents_project ON documents(project_id);
CREATE INDEX idx_documents_status ON documents(parse_status);
```

#### document_chunks

```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(32) NOT NULL,   -- paragraph | section
    content TEXT NOT NULL,
    token_count INT,
    metadata JSONB NOT NULL,           -- {page_start, page_end, section_title, paragraph_index}
    embedding_id VARCHAR(256),         -- 向量数据库中对应的 ID
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_chunks_type ON document_chunks(chunk_type);
```

#### analysis_tasks

```sql
CREATE TABLE analysis_tasks (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    type VARCHAR(64) NOT NULL,         -- literature_review | policy_draft | policy_comparison | tech_interpretation
    title VARCHAR(512) NOT NULL,
    description TEXT,
    status VARCHAR(32) DEFAULT 'pending',  -- pending | running | completed | failed | cancelled
    params JSONB NOT NULL,             -- 分析参数（知识源、焦点等）
    llm_route VARCHAR(32),             -- local | cloud | auto
    sensitivity VARCHAR(32),           -- high | low
    progress JSONB,                    -- {step, step_index, total_steps_estimate, message}
    iteration_count INT DEFAULT 0,
    error_message TEXT,
    celery_task_id VARCHAR(256),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_tasks_project ON analysis_tasks(project_id);
CREATE INDEX idx_tasks_status ON analysis_tasks(status);
```

#### task_outputs

```sql
CREATE TABLE task_outputs (
    id UUID PRIMARY KEY,
    task_id UUID REFERENCES analysis_tasks(id) ON DELETE CASCADE,
    format VARCHAR(32) NOT NULL,       -- markdown | docx | xlsx | pptx
    content TEXT,                      -- Markdown 格式直接存（其他格式存路径）
    storage_path VARCHAR(1024),        -- MinIO 对象路径（二进制格式）
    created_at TIMESTAMP DEFAULT now()
);
```

#### citations

```sql
CREATE TABLE citations (
    id UUID PRIMARY KEY,
    task_output_id UUID REFERENCES task_outputs(id) ON DELETE CASCADE,
    sentence_index INT NOT NULL,       -- 在输出文本中的句子序号
    ref_id VARCHAR(128) NOT NULL,      -- LLM 生成的唯一引用标记
    source_text TEXT,                  -- 输出句子文本
    chunk_ids UUID[],                  -- 关联的 document_chunks
    document_ids UUID[],               -- 关联的 documents
    page_ranges VARCHAR(256)[],        -- 页码范围数组
    confidence VARCHAR(32),            -- direct | fuzzy | uncertain
    verified_by UUID REFERENCES users(id),  -- 如果人工审核过
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_citations_output ON citations(task_output_id);
CREATE INDEX idx_citations_confidence ON citations(confidence);
```

#### audit_logs

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    action VARCHAR(128) NOT NULL,       -- login | logout | create_project | upload_document | create_task | export_output | ...
    resource_type VARCHAR(64),          -- project | document | task | output | user | group
    resource_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
```

---

## 7. Agent 编排引擎设计

### 7.1 引擎架构

```
┌────────────────────────────────────────────────────────┐
│                    Agent Engine                        │
│                                                       │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐  │
│  │ ToolRegistry│   │ StateManager│   │ LoopRunner  │  │
│  │             │   │             │   │             │  │
│  │ search_kb   │   │ messages[]  │   │ while not   │  │
│  │ generate_   │   │ chunks[]    │   │  terminal:  │  │
│  │   section   │   │ sections[]  │   │   think()   │  │
│  │ verify_     │   │ citations{} │   │   act()     │  │
│  │   citations │   │ plan        │   │   observe() │  │
│  │ format_     │   │ iteration   │   │             │  │
│  │   output    │   │             │   │             │  │
│  └─────────────┘   └─────────────┘   └─────────────┘  │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Prompt Templates                    │  │
│  │                                                 │  │
│  │  literature_review.j2                           │  │
│  │  policy_draft.j2                                │  │
│  │  policy_comparison.j2                           │  │
│  │  tech_interpretation.j2                         │  │
│  └─────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

### 7.2 核心循环伪代码

```python
class AgentEngine:
    MAX_ITERATIONS = 5
    MAX_RETRIEVED_CHUNKS = 30

    async def run(self, task: AnalysisTask, kb_sources: list[KBSource]) -> TaskOutput:
        state = AgentState(
            task=task,
            kb_sources=kb_sources,
            messages=[self._build_system_message(task)],  # system prompt
            retrieved_chunks=[],
            generated_sections=[],
            citations={},
            plan=""
        )

        while state.iteration < self.MAX_ITERATIONS:
            # Step 1: Plan — LLM decides what to do next
            plan = await self._plan(state)
            state.plan = plan

            if plan.action == "finish":
                break

            # Step 2: Execute tool
            result = await self._execute_tool(plan.tool_name, plan.tool_args, state)

            # Step 3: Observe and update state
            state = self._update_state(state, plan.tool_name, result)
            state.iteration += 1
            self._report_progress(task, state)

        # Final: format output
        return await self._format_output(state, task.output_formats)

    async def _plan(self, state: AgentState) -> Plan:
        """LLM 规划下一步行动"""
        messages = self._build_planning_messages(state)
        response = await llm_router.chat(messages, tools=self.tools_definitions)
        return parse_plan(response)  # 解析 LLM 返回的 tool_call 或 finish 信号

    async def _execute_tool(self, tool_name: str, args: dict, state: AgentState):
        match tool_name:
            case "search_kb":
                return await kb_service.hybrid_search(
                    query=args["query"],
                    kb_sources=state.kb_sources,
                    top_k=10
                )
            case "generate_section":
                return await self._generate_with_citations(
                    section_goal=args["section_goal"],
                    context=state.retrieved_chunks,
                    generated_so_far=state.generated_sections
                )
            case "verify_citations":
                return await citation_service.verify(
                    text=args["text"],
                    available_chunks=state.retrieved_chunks
                )
            case "extract_key_claims":
                return await self._extract_claims(
                    text=args["text"]
                )
            case "compare_policies":
                return await self._compare(
                    policies=args["policies"],
                    context=state.retrieved_chunks
                )
```

### 7.3 提示词模板示例（文献综述）

```jinja2
# System

你是 EconAI 经济政策分析助手。你的任务是撰写一份基于给定文献的综述报告。

## 当前任务
{{ task.title }}
{{ task.description }}

## 知识源
本次分析基于以下文档（已上传至知识库）：
{% for doc in task.kb_sources.documents %}
- [{{ doc.id }}] {{ doc.filename }} ({{ doc.metadata.title }})
{% endfor %}

## 输出要求
1. 所有基于文献的断言必须使用 [ref:doc_id:page_range] 格式标注来源
2. 不确定的推断使用 [ref:uncertain] 标注
3. 综述结构应包括：研究背景、核心论点比较、方法论评估、政策建议汇总、研究空白

## 可用工具
- search_kb: 检索知识库中相关内容
- generate_section: 生成指定章节内容
- verify_citations: 校验引用准确性
- extract_key_claims: 提取文献核心论点

## 工作原则
- 优先使用 search_kb 获取信息，再做生成
- 每个章节至少检索一次相关信息
- 不同文献的观点冲突必须显式标注
- 标注每篇文献的方法论质量和证据强度
```

---

## 8. 安全架构

### 8.1 分层安全模型

```
┌────────────────────────────────────────┐
│  网络层                                  │
│  - 仅内网可访问（VPN/内网IP）              │
│  - Nginx 反向代理，TLS 终结               │
│  - WAF（可选）                            │
├────────────────────────────────────────┤
│  应用层                                  │
│  - JWT 认证（access: 2h, refresh: 24h）   │
│  - LDAP/SSO 对接机构账号体系              │
│  - RBAC 细粒度权限                        │
│  - 项目组间数据隔离                        │
│  - API 频率限制（每用户 100 req/min）      │
│  - 输入校验和参数化查询（防注入）           │
├────────────────────────────────────────┤
│  数据层                                  │
│  - PostgreSQL: AES-256 存储加密           │
│  - MinIO: 服务端加密 + 传输加密            │
│  - 敏感数据标记：标记为 internal 的文档     │
│    自动路由到本地 LLM                      │
│  - 数据库连接白名单                        │
├────────────────────────────────────────┤
│  审计层                                  │
│  - 所有操作记录至 audit_logs              │
│  - 日志保留 6 个月（等保二级要求）          │
│  - 不可删除/篡改的审计日志                 │
│  - Prometheus 监控 + 异常告警             │
└────────────────────────────────────────┘
```

### 8.2 数据隔离实现

```python
# 知识库检索时的数据隔离
async def search_kb(query: str, kb_sources: list[KBSource], user: User) -> list[Chunk]:
    accessible_projects = await get_user_project_ids(user)
    
    filters = []
    for source in kb_sources:
        if source.type == "project":
            if source.project_id not in accessible_projects:
                raise PermissionDenied(f"无权访问项目 {source.project_id}")
            filters.append({"project_id": source.project_id})
        elif source.type == "institutional":
            if not user.group_id in source.allowed_groups:
                raise PermissionDenied(f"无权访问该机构知识库分区")
            filters.append({"kb_type": "institutional", "group_id": user.group_id})
    
    return await vector_search(query, filters=filters)
```

### 8.3 GDPR 相关设计

| GDPR 要求 | 实现 |
|-----------|------|
| 数据访问权 | API: GET /api/user/data |
| 数据删除权 | API: DELETE /api/user/data（级联删除项目、文档、任务结果） |
| 数据可携带 | API: GET /api/user/data/export（JSON 格式导出） |
| 同意管理 | 登录时收集处理同意，可随时撤回 |
| 数据最小化 | 仅存储分析必需的文档和元数据 |
| DPIA | 系统上线前完成数据保护影响评估 |

---

## 9. 部署架构

### 9.1 部署拓扑

```
                    ┌─────────────────────┐
                    │    机构内网          │
                    │                     │
  用户浏览器 ──TLS──→│  ┌───────────────┐  │
                    │  │  Nginx (LB)   │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────┴───────┐  │
                    │  │  FastAPI × N  │  │
                    │  │  (Gunicorn +  │  │
                    │  │   Uvicorn)    │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────┴──────────────┐  │
                    │  │       Services        │  │
                    │  │  ┌────────┐           │  │
                    │  │  │Celery  │           │  │
                    │  │  │Worker  │           │  │
                    │  │  │× N     │           │  │
                    │  │  └────────┘           │  │
                    │  └──────────────────────┘  │
                    │          │                 │
                    │  ┌───────┴──────────────┐  │
                    │  │      Data Stores      │  │
                    │  │  PostgreSQL  Milvus   │  │
                    │  │  Redis       MinIO    │  │
                    │  └──────────────────────┘  │
                    │          │                 │
                    │  ┌───────┴──────────────┐  │
                    │  │    GPU Cluster        │  │
                    │  │  ┌──────────────────┐ │  │
                    │  │  │ vLLM / Ollama    │ │  │
                    │  │  │ (Qwen/DeepSeek/  │ │  │
                    │  │  │  Llama)          │ │  │
                    │  │  └──────────────────┘ │  │
                    │  └──────────────────────┘  │
                    │          │                 │
                    └──────────┼─────────────────┘
                               │
                        ┌──────┴──────┐
                        │ Claude API  │  (出站，仅非敏感数据)
                        │ (Internet)  │
                        └─────────────┘
```

### 9.2 容器化部署

```
econai/
├── docker-compose.yml
├── services/
│   ├── api/          # FastAPI 应用
│   ├── worker/       # Celery Worker
│   ├── nginx/        # 反向代理
│   ├── postgres/     # 数据库
│   ├── redis/        # 队列 + 缓存
│   ├── milvus/       # 向量数据库
│   ├── minio/        # 对象存储
│   └── prometheus/   # 监控
```

### 9.3 资源规划（预估）

| 组件 | 资源 | 说明 |
|------|------|------|
| FastAPI | 4 vCPU, 8 GB RAM × 2 实例 | 承载 < 20 并发，含峰值余量 |
| Celery Worker | 4 vCPU, 8 GB RAM × 3 实例 | 并行处理文档解析和 Agent 任务 |
| PostgreSQL | 8 vCPU, 32 GB RAM, 1 TB SSD | 5 万+ 文档元数据 + 业务数据 |
| Milvus/Qdrant | 8 vCPU, 32 GB RAM, 2 TB SSD | 10 万级向量索引 |
| MinIO | 4 vCPU, 16 GB RAM, 8 TB HDD | 原始文档存储 |
| Redis | 2 vCPU, 8 GB RAM | 队列 + 缓存 |
| GPU (本地 LLM) | 2× A100 80GB 或等效 | 本地模型推理 |
| **总计（不含 GPU）** | ~34 vCPU, ~112 GB RAM, ~11 TB 存储 | |

---

## 10. 技术栈总览

| 层次 | 技术 | 版本参考 | 选型依据 |
|------|------|----------|----------|
| 前端 | React | 19.x | 已确认 |
| 前端语言 | TypeScript | 5.x | 已确认 |
| UI 组件库 | Ant Design / Shadcn | latest | 企业级 CRUD + 复杂表格 |
| 后端框架 | FastAPI | 0.115+ | 异步高性能，Python 生态 |
| ASGI 服务器 | Gunicorn + Uvicorn | - | 生产级部署 |
| 业务数据库 | PostgreSQL | 16+ | 全文搜索、JSONB、成熟稳定 |
| 向量数据库 | Milvus / Qdrant | - | 10 万级规模 |
| 对象存储 | MinIO | latest | S3 兼容，私有化 |
| 任务队列 | Celery + Redis | 5.x / 7.x | Python 标准异步方案 |
| 文档解析 | Unstructured + python-docx + PyMuPDF | - | 多格式覆盖 |
| OCR | Tesseract | 5.x | 已确认，chi_sim 语言包 |
| Embedding | text2vec / m3e | - | 已确认，中文开源 |
| Reranker | BGE-Reranker | - | 中文重排序 |
| 本地 LLM 推理 | vLLM / Ollama | - | OpenAI 兼容 API |
| 云端 LLM | Anthropic Claude API | - | 已确认 |
| .docx 生成 | python-docx | 1.x | GB/T 9704 模板 |
| 监控 | Prometheus + Grafana | - | 标准运维栈 |
| 容器化 | Docker + Docker Compose | - | 私有化部署 |

---

## 11. 关键风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| Agent 循环不稳定（LLM 输出格式不可控） | 分析任务失败或结果不可用 | 中 | 固定迭代上限 + tool_call 解析的容错 + fallback 到固定流水线 |
| 本地 LLM 推理速度不满足性能要求 | 分析任务超时 | 中 | GPU 集群已有，优先评测算力；必要时降级使用更小的模型 |
| inline 引用格式不准确（LLM 编造页码） | 溯源不可信 | 高 | CitationVerifier 后置校验 + 不匹配的引用标记为 uncertain |
| GB/T 9704 排版复杂性 | 导出 .docx 格式不符合要求 | 中 | 与机构协作获取模板文件，减少自研排版逻辑 |
| 混合检索召回质量不佳 | 生成内容缺乏充分证据支撑 | 中 | 监控检索召回率，逐步调优 RRF 参数和 Reranker 模型 |
| Claude API 跨境数据传输合规 | GDPR 合规风险 | 低 | 与法务确认 SCC 机制，MVP 阶段先默认全走本地 LLM |

---

*文档版本：v1.0 | 日期：2026-05-17 | 基于需求文档 v2.0（终稿）*