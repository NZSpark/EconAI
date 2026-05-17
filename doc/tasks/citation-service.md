# M6: 来源溯源服务 任务清单

> 目录：`services/citation-service/` | 服务端口：8005

## 任务列表

### 项目初始化
- [ ] M6-01 初始化 FastAPI 项目结构，创建 `services/citation-service/` 目录，配置依赖
- [ ] M6-02 创建配置管理模块（相似度阈值 0.85、批量校验大小、脚注/尾注默认设置）

### Inline 引用解析
- [ ] M6-03 实现句子分割器：中英文标点分割（。！？.!?），保留句子边界
- [ ] M6-04 实现 [ref:...] 正则提取器：匹配单引用 `[ref:doc_id:page_range]`、多引用 `[ref:doc_id:page|doc_id:page]`、不确定声明 `[ref:uncertain]`
- [ ] M6-05 实现引用标记解析：doc_id + page_range 提取，多引用按 `|` 拆分
- [ ] M6-06 实现 CitationParser 主流程：文本 → 分句 → 提取引用 → 建立 sentence → doc_refs 映射
- [ ] M6-07 处理边界情况：无引用标记的文本正常返回空列表；格式异常的 ref 记录 parse_error

### 引用校验
- [ ] M6-08 实现页码范围匹配：chunk.page_start ≤ ref.page_start 且 chunk.page_end ≥ ref.page_end 判定为匹配
- [ ] M6-09 实现页面重叠度计算：当精确匹配失败时，计算 page_overlap(chunk.pages, ref.pages)
- [ ] M6-10 实现语义相似度校验：对引用的 sentence 和 chunk.content 计算 embedding cosine similarity
- [ ] M6-11 实现置信度判定逻辑：精确页面匹配 + 语义相似度>0.85 → direct；仅有语义相似度>0.85 → fuzzy；无匹配 → uncertain
- [ ] M6-12 实现 CitationVerifier 主流程：遍历 parsed_citations → 查 matching_chunks → 计算相似度 → 标记置信度
- [ ] M6-13 生成校验报告 summary（总数/direct 数/fuzzy 数/uncertain 数）

### 引用校验 API
- [ ] M6-14 实现校验端点 `POST /internal/citations/verify`：接收 text + context_chunk_ids → 返回 verified citations
- [ ] M6-15 校验端点返回每条约用的 matched_chunks（含 chunk_id/document_id/page_start/page_end/excerpt/similarity）

### 引用查询 API
- [ ] M6-16 实现引用列表端点 `GET /api/tasks/{task_id}/output/citations`（支持按 confidence 过滤）
- [ ] M6-17 实现引用详情端点 `GET /api/tasks/{task_id}/output/citations/{citation_id}`（含原文摘录）
- [ ] M6-18 引用详情包含：sentence、confidence、source(document_id/title/pages/excerpt)、verified_at、verified_by

### 引用格式化
- [ ] M6-19 实现 Markdown 引用格式化：将 [ref:...] 替换为 GFM 脚注 `[^n]`，文末追加引用清单
- [ ] M6-20 实现 Web 预览引用数据生成：前端通过 API 获取 citation JSON，渲染悬浮 tooltip
- [ ] M6-21 实现 .docx 脚注格式化：生成脚注文本列表，供 output-service 写入 python-docx footnotes
- [ ] M6-22 实现 .xlsx 引用清单格式化：生成 "引用清单" sheet 数据（序号/来源/页码/置信度）
- [ ] M6-23 实现 .pptx 引用格式化：生成每页底部小字引用文本 + 末页完整清单

### 引用数据持久化
- [ ] M6-24 实现 citations 表写入：校验完成后将结果批量写入 PostgreSQL (task_output_id, ref_id, sentence, confidence, chunk_ids, page_ranges)
- [ ] M6-25 实现 citations 表查询：按 task_output_id 查询，按 confidence 过滤

### 测试
- [ ] M6-26 编写 inline 引用正则解析测试（单引用/多引用/uncertain/混合/无引用/异常格式）
- [ ] M6-27 编写页码匹配测试（精确匹配/范围匹配/重叠度计算/完全不匹配）
- [ ] M6-28 编写置信度判定测试（direct/fuzzy/uncertain 三档边界）
- [ ] M6-29 编写引用校验端到端测试（输入带引用文本 → 返回校验结果）
- [ ] M6-30 编写引用格式化测试（Markdown 脚注生成正确性）