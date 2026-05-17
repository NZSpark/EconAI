# M7: 输出生成服务 任务清单

> 目录：`services/output-service/` | 服务端口：8006

## 任务列表

### 项目初始化
- [ ] M7-01 初始化 FastAPI 项目结构，创建 `services/output-service/` 目录，配置依赖（python-docx, openpyxl, python-pptx, jinja2）
- [ ] M7-02 创建配置管理模块（MinIO 输出路径、机构名称、默认字体、文件大小上限、模板目录）
- [ ] M7-03 创建输出格式模板目录 `templates/output/`，放置样式配置文件

### MinIO 输出存储
- [ ] M7-04 实现 MinIO 输出上传客户端：upload/download/get_presigned_url
- [ ] M7-05 实现 task_outputs 表 CRUD：生成后写入记录（task_id, format, content/storage_path）

### Markdown 生成
- [ ] M7-06 实现 Markdown 模板（Jinja2）：YAML front-matter + 章节标题（#/##/###） + 正文 + 引用脚注
- [ ] M7-07 实现 [ref:...] → `[^n]` 脚注替换逻辑
- [ ] M7-08 实现文末 "参考文献" 章节自动生成（从 citations 数据渲染格式：[n] 作者. 标题. 来源. 页码. 置信度）

### .docx 生成 (GB/T 9704)
- [ ] M7-09 实现 GB/T 9704 公文样式定义：二号小标宋体（标题）、三号黑体（一级标题）、三号楷体（二级标题）、三号仿宋（正文）
- [ ] M7-10 实现版头区域：发文机关标志（页眉）+ 发文字号 + 签发人（右对齐）
- [ ] M7-11 实现主体区域：标题（居中）+ 主送机关（可选，顶格）+ 正文（首行缩进2字符，1.5倍行距）
- [ ] M7-12 实现正文中引用角标渲染（上标 [1][2]）
- [ ] M7-13 实现附件说明段落
- [ ] M7-14 实现版记区域（页脚）：抄送机关 + 印发日期
- [ ] M7-15 实现文末 "参考文献" 引用清单
- [ ] M7-16 实现脚注/尾注模式切换（python-docx footnote，根据配置选择）

### .xlsx 生成
- [ ] M7-17 实现对比分析 Sheet（Sheet 1）：行=政策选项，列=比较维度，单元格=分析文本，带样式（表头加粗/边框/自动列宽）
- [ ] M7-18 实现引用清单 Sheet（Sheet 2）：序号/来源文档/页码范围/置信度
- [ ] M7-19 实现数据摘要 Sheet（Sheet 3，可选）：关键指标和统计数据

### .pptx 生成
- [ ] M7-20 实现封面 Slide：标题 + 副标题 + 日期
- [ ] M7-21 实现目录/概述 Slide
- [ ] M7-22 实现关键发现 Slides（每个发现 1 页）：标题 + bullet points + 底部小字引用
- [ ] M7-23 实现政策建议/结论 Slide
- [ ] M7-24 实现末页完整引用清单 Slide

### 格式模板管理
- [ ] M7-25 实现 docx_gbt9704.yaml 模板：定义所有段落样式（字体/字号/间距/缩进/对齐）
- [ ] M7-26 实现 pptx_briefing.yaml 模板：定义幻灯片母版样式、占位符位置
- [ ] M7-27 实现 xlsx_matrix.yaml 模板：定义表头样式、数据区样式、列宽规则
- [ ] M7-28 实现模板加载器：从 YAML 文件读取样式配置，fallback 到代码内置默认值

### 生成 API
- [ ] M7-29 实现内部生成端点 `POST /internal/output/generate`：接收 sections + citations + metadata + formats → 生成各格式文件
- [ ] M7-30 实现格式路由器：根据 formats 数组并行生成多种格式
- [ ] M7-31 生成完成后写入 PostgreSQL task_outputs + 上传 MinIO

### 输出与导出 API
- [ ] M7-32 实现输出预览端点 `GET /api/tasks/{task_id}/output`（Markdown 格式，代理到 orchestration-service）
- [ ] M7-33 实现文件导出端点 `GET /api/tasks/{task_id}/export?format=docx|md|xlsx|pptx`：从 MinIO 读取 → 返回文件流
- [ ] M7-34 设置正确的 Content-Type 和 Content-Disposition header（中文文件名 URL 编码）

### 测试
- [ ] M7-35 编写 Markdown 生成测试（章节结构 + 脚注替换 + 引用清单）
- [ ] M7-36 编写 .docx GB/T 9704 格式测试（字体/字号/缩进/行距/页眉页脚）
- [ ] M7-37 编写 .xlsx 生成测试（多 sheet + 样式）
- [ ] M7-38 编写 .pptx 生成测试（slide 数量 + 内容正确性）
- [ ] M7-39 编写模板加载和 fallback 测试