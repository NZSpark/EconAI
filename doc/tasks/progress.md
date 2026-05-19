# EconAI 总体进度

> 版本：v1.0 | 日期：2026-05-17 | 基于需求文档 v2.0 + 概要设计 v1.0 + 详细设计 v1.0

## 模块进度

| 编号 | 模块 | 目录 | 子任务数 | 状态 |
|------|------|------|----------|------|
| M1 | API 网关 | `api-gateway/` | 28 | [x] 已完成 (28/28) |
| M2 | 文档解析服务 | `services/document-service/` | 43 | [x] 已完成 (43/43) |
| M3 | 知识库服务 | `services/kb-service/` | 35 | [ ] 未开始 |
| M4 | 任务编排服务 | `services/orchestration-service/` | 54 | [ ] 未开始 |
| M5 | LLM 路由服务 | `services/llm-router/` | 33 | [x] 已完成 (33/33) |
| M6 | 来源溯源服务 | `services/citation-service/` | 30 | [x] 已完成 (30/30) |
| M7 | 输出生成服务 | `services/output-service/` | 39 | [x] 已完成 (39/39) |
| M8 | 用户权限服务 | `services/user-service/` | 42 | [x] 已完成 (42/42) |
| M9 | 前端 SPA | `frontend/` | 38 | [ ] 未开始 |
| M10 | 基础设施与部署 | 项目根目录 | 34 | [x] 已完成 (34/34) |

**总计子任务：376** | **已完成：249** | **完成率：66.2%**

## 依赖关系

```
M10 (基础设施)    ← 需要最先完成（开发环境）
    │
    ├── M8 (用户权限)   ← 认证依赖
    ├── M5 (LLM 路由)   ← 无业务依赖
    │
    ├── M1 (API 网关)   ← 依赖 M8 的认证接口
    │
    ├── M2 (文档解析)   ← 依赖 M10 (MinIO, PostgreSQL)
    │     │
    │     └── M3 (知识库) ← 依赖 M2 的索引事件 + M5 (embedding)
    │
    ├── M6 (来源溯源)   ← 无业务依赖
    ├── M7 (输出生成)   ← 依赖 M6 的引用格式化
    │
    └── M4 (任务编排)   ← 依赖 M3, M5, M6, M7（核心大脑，最晚集成）
          │
          └── M9 (前端)  ← 依赖 M1 的 API 完成
```

## 建议开发顺序

### 第一阶段：基础设施 + 基础服务（第 1-2 周）
1. **M10** 基础设施 — Docker Compose, PostgreSQL, Redis, MinIO, Milvus, Nginx
2. **M8** 用户权限服务 — 认证、RBAC、用户/组管理
3. **M5** LLM 路由服务 — 适配器、路由决策

### 第二阶段：网关 + 数据处理（第 3-4 周）
4. **M1** API 网关 — 认证中间件、限流、审计、路由
5. **M2** 文档解析服务 — 多格式解析、分块
6. **M3** 知识库服务 — embedding、混合检索

### 第三阶段：核心智能 + 周边（第 5-7 周）
7. **M6** 来源溯源服务 — 引用解析、校验、格式化
8. **M7** 输出生成服务 — 多格式生成、GB/T 9704

### 第四阶段：编排 + 前端（第 8-10 周）
9. **M4** 任务编排服务 — Agent 引擎、工作流
10. **M9** 前端 SPA — 全功能 UI

## 任务文件索引

- [M1: API 网关](api-gateway.md)
- [M2: 文档解析服务](document-service.md)
- [M3: 知识库服务](kb-service.md)
- [M4: 任务编排服务](orchestration-service.md)
- [M5: LLM 路由服务](llm-router.md)
- [M6: 来源溯源服务](citation-service.md)
- [M7: 输出生成服务](output-service.md)
- [M8: 用户权限服务](user-service.md)
- [M9: 前端 SPA](frontend.md)
- [M10: 基础设施与部署](infrastructure.md)