# M5: LLM 路由服务 任务清单

> 目录：`services/llm-router/` | 服务端口：8004

## 任务列表

### 项目初始化
- [x] M5-01 初始化 FastAPI 项目结构，创建 `services/llm-router/` 目录，配置依赖（anthropic SDK, httpx）
- [x] M5-02 创建配置管理模块（ANTHROPIC_API_KEY、本地 LLM 端点、默认模型、超时、重试参数）

### 模型注册表
- [x] M5-03 实现 ModelRegistry：维护可用模型列表，包含 id/provider/type/capabilities 字段
- [x] M5-04 实现模型列表端点 `GET /internal/llm/models`：返回可用模型 + default_local + default_cloud
- [x] M5-05 支持模型配置热加载（从 YAML/JSON 配置文件读取，无需重启）

### 路由决策
- [x] M5-06 实现路由决策引擎：model=="auto" → 按 sensitivity 路由（high→local, low→cloud），model 指定 → 直接使用
- [x] M5-07 实现路由原因记录：每次路由决策记录 target + reason 字段到响应中
- [x] M5-08 实现 Claude API 故障降级：cloud 调用连续失败 → 自动降级到 local（如果 sensitivity 允许）

### Claude 适配器
- [x] M5-09 实现 ClaudeAdapter：将统一请求格式转换为 Anthropic Messages API 格式
- [x] M5-10 处理 system message（Anthropic 独立 system 字段）
- [x] M5-11 处理 tool_use 双向转换：统一 tool 定义 → Anthropic tool format，Anthropic tool_use → 统一 tool_calls 格式
- [x] M5-12 处理 Anthropic 流式响应（stream=true 时，聚合后返回）
- [x] M5-13 处理 Anthropic 错误响应（rate_limit/overloaded → 429，auth_error → 500）

### 本地适配器
- [x] M5-14 实现 LocalAdapter：将统一请求格式转换为 OpenAI-compatible `/v1/chat/completions` 格式
- [x] M5-15 处理本地模型的 tool calling（function-calling 格式双向转换）
- [x] M5-16 处理本地模型流式响应
- [x] M5-17 处理本地模型 OOM/不可用（返回 503 + 等待重试提示）

### 统一 Chat Completion 端点
- [x] M5-18 实现内部端点 `POST /internal/llm/chat`：接收统一请求格式 → 路由 → 适配器 → 返回统一响应格式
- [x] M5-19 实现请求参数校验：messages 非空、temperature 范围、max_tokens 上限
- [x] M5-20 实现 token 超限时的消息截断：保留 system + 最近 N 条 messages

### Token 追踪
- [x] M5-21 实现 token 使用量记录：每次调用后记录 prompt_tokens/completion_tokens/total_tokens/latency_ms/model/routing
- [x] M5-22 实现 token 使用量持久化：写入 llm_usage_logs 表（或通过 Redis pub/sub 异步写入）
- [x] M5-23 实现 token 使用统计聚合查询（按 user_id/task_id/model 维度）

### 重试与容错
- [x] M5-24 实现 429 速率限制重试：指数退避（base=2s），最多 3 次
- [x] M5-25 实现 5xx 错误重试：线性退避（1s），最多 2 次，第 2 次可降级到本地
- [x] M5-26 实现请求超时处理（120s）：超时 → 重试 1 次 → 仍超时返回 504
- [x] M5-27 实现熔断器模式：连续失败 N 次后，短时间内直接返回 503（避免雪崩）

### 测试
- [x] M5-28 编写路由决策逻辑测试（auto/local/cloud + sensitivity high/low 组合）
- [x] M5-29 编写 ClaudeAdapter 请求/响应格式转换测试（含 tool_use）
- [x] M5-30 编写 LocalAdapter OpenAI 格式转换测试（含 function-calling）
- [x] M5-31 编写降级策略测试（Claude 不可达 → 自动切本地）
- [x] M5-32 编写重试和熔断器测试
- [x] M5-33 编写 token 超限截断测试