# M2: 文档解析服务 任务清单

> 目录：`services/document-service/` | 服务端口：8001

## 任务列表

### 项目初始化
- [x] M2-01 初始化 FastAPI 项目结构，创建 `services/document-service/` 目录，配置依赖
- [x] M2-02 创建配置管理模块（MinIO 地址/bucket、chunk 参数、OCR 语言、文件大小限制）
- [x] M2-03 配置 Celery worker 启动入口，注册 `document` 队列

### 文档上传
- [x] M2-04 实现文档上传端点 `POST /api/projects/{project_id}/documents`（multipart/form-data）
- [x] M2-05 实现文件校验：扩展名白名单、MIME 类型校验、文件大小上限（100MB）、magic bytes 校验
- [x] M2-06 实现 MinIO 存储客户端封装（upload/download/delete），bucket 自动创建
- [x] M2-07 上传成功后写入 documents 表（status=pending），触发 Celery 异步解析任务

### 格式识别
- [x] M2-08 实现格式识别器：magic bytes 检测 + 扩展名兜底，输出统一 format 枚举（pdf/docx/xlsx/pptx/eml/html/md/txt/image）
- [x] M2-09 PDF 文本层检测：通过 PyMuPDF 判断是否有可提取文本层，无文本层标记为需要 OCR

### 内容提取
- [x] M2-10 实现 PDF 解析器（PyMuPDF/pdfplumber）：提取全文文本 + 页码 + 表格 + 图片位置
- [x] M2-11 实现 Word 解析器（python-docx）：提取全文文本 + 段落样式（标题/正文）+ 表格
- [x] M2-12 实现 Markdown/纯文本解析器：保留标题层级结构
- [x] M2-13 实现 Excel/CSV 解析器（openpyxl/pandas）：提取结构化表格 + 列名 + sheet 名
- [x] M2-14 实现 PowerPoint 解析器（python-pptx）：逐页提取文本 + 备注
- [x] M2-15 实现邮件解析器（email 标准库）：提取正文 + 元数据（发件人/日期/主题/收件人）
- [x] M2-16 实现 HTML/MHTML 解析器（BeautifulSoup）：提取正文（去除导航/广告/脚本）+ 原始链接
- [x] M2-17 实现 Tesseract OCR 处理器：图片 PDF/图片文件 → 文本（chi_sim+eng），保留页码映射
- [x] M2-18 实现解析器路由器：根据格式自动选择解析器，返回统一的结构化文本对象
- [x] M2-18a 实现共享图片提取+OCR 核心模块（image_extractor.py）：从 PDF/DOCX/PPTX/HTML 中提取嵌入图片并执行 OCR 识别
- [x] M2-18b 增强 PDF 解析器：提取嵌入图片并通过 OCR 识别文字，追加到对应页面内容
- [x] M2-18c 增强 Word 解析器：提取 docx 中嵌入的图片并通过 OCR 识别，追加到全文
- [x] M2-18d 增强 PPT 解析器：提取幻灯片中嵌入的图片并通过 OCR 识别，追加到对应幻灯片
- [x] M2-18e 增强 HTML 解析器：提取 data-URI 内嵌图片（base64 编码）并通过 OCR 识别
- [x] M2-18f ParsedContent 模型新增 ocr_images 字段：记录每次 OCR 的审计追踪（页码/图片索引/OCR 文本/格式/尺寸）

### 元数据提取
- [x] M2-19 实现元数据提取器：标题（文件名/文档属性/首行推断）、作者、日期、来源、页数
- [x] M2-20 实现 PDF 内置元数据提取（/Title, /Author, /CreationDate）
- [x] M2-21 实现 Word 内置属性提取（title, author, created, modified）

### 多粒度分块
- [x] M2-22 实现 token 计数器（基于 tiktoken 或字符估算），支持中英文混合
- [x] M2-23 实现自然段落分割器：按 `\n\n` 分割，保持段落完整性
- [x] M2-24 实现段落级分块器：目标 300 token，最小 100，最大 500，相邻重叠 50 token，按句子边界对齐
- [x] M2-25 实现章节结构检测器：识别标题层级（PDF 书签/Word 样式/Markdown heading）
- [x] M2-26 实现章节级分块器：目标 2000 token，最小 500，最大 3000，相邻重叠 100 token，按章节边界对齐
- [x] M2-27 实现分块元数据生成：page_start, page_end, section_title, paragraph_index, chunk_index

### 状态机与存储
- [x] M2-28 实现文档状态机：pending → parsing → ready/error（含状态转换校验）
- [x] M2-29 分块结果写入 document_chunks 表（批量 INSERT）
- [x] M2-30 解析完成后更新 documents 表（parse_status=ready, page_count, metadata JSONB）

### 索引事件
- [x] M2-31 实现 Redis pub/sub 发布：解析完成后向 `kb:index:request` 频道发送索引事件
- [x] M2-32 索引事件包含 document_id, project_id, chunk_ids, is_internal, timestamp

### CRUD 端点
- [x] M2-33 实现文档列表端点 `GET /api/projects/{project_id}/documents`（分页 + 状态/格式过滤）
- [x] M2-34 实现文档详情端点 `GET /api/projects/{project_id}/documents/{document_id}`
- [x] M2-35 实现文档删除端点 `DELETE /api/projects/{project_id}/documents/{document_id}`（级联：MinIO + chunks + 向量）
- [x] M2-36 实现重新索引端点 `POST /api/projects/{project_id}/documents/{document_id}/reindex`

### 错误处理
- [x] M2-37 实现解析错误处理：捕获异常 → parse_status=error → 记录 parse_error 详情
- [x] M2-38 实现不支持的格式返回 DOC_FORMAT_UNSUPPORTED 错误码

### 测试
- [x] M2-39 编写各格式解析器单元测试（PDF/Word/Markdown/Excel/PPT/Email/HTML）
- [x] M2-40 编写 OCR 解析测试（含中文内容图片 PDF）
- [x] M2-41 编写分块边界测试（段落级/章节级 token 范围、overlap 正确性）
- [x] M2-42 编写文档状态机转换测试
- [x] M2-43 编写上传→解析→索引事件 集成测试
- [x] M2-44 编写图片提取+OCR 单元测试（ocr_image_bytes、PDF/DOCX/PPTX/HTML 图片提取、ocr_images 字段、内容增强验证，共 24 个测试用例）