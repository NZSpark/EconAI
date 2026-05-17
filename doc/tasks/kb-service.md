# M3: 知识库服务 任务清单

> 目录：`services/kb-service/` | 服务端口：8002

## 任务列表

### 项目初始化
- [ ] M3-01 初始化 FastAPI 项目结构，创建 `services/kb-service/` 目录，配置依赖
- [ ] M3-02 创建配置管理模块（向量数据库类型/地址、embedding 模型、RRF 参数、搜索超时）

### Embedding 生成
- [ ] M3-03 实现 Embedding 客户端封装，支持 text2vec-large-chinese / m3e，输出 768d 或 1024d 向量
- [ ] M3-04 实现批量 embedding 生成（batch_size 可配置），含 token 超限截断保护
- [ ] M3-05 实现 embedding 缓存层（Redis），相同文本不重复计算

### 向量数据库
- [ ] M3-06 实现 Milvus/Qdrant 客户端封装（统一接口，通过配置切换），支持 collection 自动创建
- [ ] M3-07 实现向量写入：chunk_id + vector + metadata（project_id, document_id, chunk_type）
- [ ] M3-08 实现向量检索：按 query_embedding 搜索 top_k=50，支持 project_id/document_id/chunk_type 过滤
- [ ] M3-09 实现向量删除：按 document_id 批量删除，级联文档删除时调用
- [ ] M3-10 实现 collection 索引配置（IVF_FLAT/HNSW），支持按 project_id 分区

### BM25 索引
- [ ] M3-11 实现 PostgreSQL FTS BM25 索引：在 document_chunks 表添加 tsvector 列 + GIN 索引
- [ ] M3-12 实现 BM25 搜索查询：中文分词 + 关键词检索 top_k=50，支持 project_id 过滤
- [ ] M3-13 实现 BM25 索引更新触发：chunk 写入/删除时自动更新 tsvector

### 混合检索
- [ ] M3-14 实现 RRF (Reciprocal Rank Fusion) 融合算法：k=60，融合向量和 BM25 结果 → top_k=30
- [ ] M3-15 实现 BGE-Reranker 重排序：对融合后的 30 条候选计算 cross-encoder 相关性分
- [ ] M3-16 实现混合检索主流程：并行向量+BM25 → RRF 融合 → Reranker 重排序 → 返回 top_k=10
- [ ] M3-17 实现搜索过滤条件构建：document_ids、chunk_types、date_range 过滤
- [ ] M3-18 实现搜索超时保护：total timeout 5s，超时返回已有结果

### 索引事件消费
- [ ] M3-19 实现 Redis pub/sub 消费者，监听 `kb:index:request` 频道
- [ ] M3-20 消费事件后执行完整索引流水线：读取 chunks → embedding → 写入向量库 → 更新 BM25 → 更新 documents.parse_status

### 知识库隔离
- [ ] M3-21 实现项目知识库搜索的 project_id 权限过滤器注入
- [ ] M3-22 实现机构知识库搜索的 group_ids 权限过滤器注入
- [ ] M3-23 权限校验失败返回 403 + USER_PERMISSION_DENIED

### API 端点
- [ ] M3-24 实现项目知识库搜索端点 `POST /api/projects/{project_id}/search`
- [ ] M3-25 实现机构知识库搜索端点 `POST /api/institutional/search`
- [ ] M3-26 实现内部搜索端点 `POST /internal/search`（供 orchestration-service 调用）

### 生命周期管理
- [ ] M3-27 实现文档索引归档：项目归档时将索引标记为 archived（不参与搜索）
- [ ] M3-28 实现文档索引恢复：项目恢复时将索引恢复为 active
- [ ] M3-29 实现文档索引删除：级联删除 chunks + 向量 + BM25 索引
- [ ] M3-30 实现项目级批量重新索引

### 测试
- [ ] M3-31 编写 embedding 生成和缓存测试
- [ ] M3-32 编写 RRF 融合算法测试（已知排序输入，验证输出）
- [ ] M3-33 编写混合检索端到端测试（向量召回 + BM25 互补验证）
- [ ] M3-34 编写知识库隔离测试（不同 project_id/group_id 的数据不可见）
- [ ] M3-35 编写索引事件消费测试（pub → 消费 → 向量库可查）