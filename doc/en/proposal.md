# PolicyAI Requirements Document

## 1. Project Overview

### 1.1 Project Positioning

PolicyAI is an AI toolkit for economic policy research institutions. It accelerates the delivery of high-quality economic policy analysis and research results by combining large language model capabilities, trusted evidence bases, project context, and transparent reasoning chains.

### 1.2 Core Differentiation

- **Information Quality Control**: Built on carefully curated data sources (internal reports, project folders, structured knowledge bases) rather than uncontrolled web content
- **Auditability**: All outputs carry sentence-level source traceability, making them traceable and reviewable in policy environments
- **Security Compliance**: Hybrid LLM deployment architecture (Claude API cloud + local model privatization), meeting Level 2 protection and GDPR compliance requirements
- **Institutional Collaboration**: Supports role-based permissions + project group isolation organizational structure

### 1.3 Key Metrics

| Metric | Description |
|--------|-------------|
| Reliability | Output assertions traceable to specific source document paragraphs/pages |
| Security | Sensitive data stays within institutional intranet, processed by local LLM; meets Level 2 protection + GDPR |
| Usability | Web interface operation, no programming background needed for complete analysis workflow |
| Scale | Supports 50K+ document index retrieval, < 20 concurrent analysts |
| Delivery | MVP prototype delivered in 1-2 months, covering all four core analysis scenarios |

---

## 2. Target Users

### 2.1 User Personas

PolicyAI targets **overall deployment in policy research institutions**, with main user roles:

| Role | Description | Typical Scenario |
|------|-------------|-----------------|
| **Policy Analyst** | Primary daily user, responsible for drafting policy documents, reviews, comparisons | Upload literature, configure knowledge base, generate analysis reports |
| **Senior Researcher** | Review analysis results, ensure academic quality | Review source annotations, verify key claims, approve report publication |
| **Project Administrator** | Manage project groups, member permissions, knowledge base resources | Create project groups, configure knowledge sources, assign user roles |
| **System Administrator** | Operations deployment, security management | Configure LLM backends, monitor system operation, audit logs |

### 2.2 Usage

- Access via **Web browser**, no client installation required
- Analyst core workflow: Create project → Configure knowledge sources → Submit analysis tasks → Review outputs → Export results
- Non-technical users can complete the full workflow; advanced users can customize analysis depth and style through prompts

---

## 3. Core Feature Scenarios

### 3.1 Literature Review

**Input**: Multiple PDF/Word policy literature, research reports, academic papers
**Process**:
1. Auto-parse document structure (sections, abstract, conclusions, references)
2. Extract core arguments, methodology, data sources, policy recommendations
3. Identify viewpoint similarities/differences and evidence conflicts between documents
4. Cluster by topic, annotate methodological quality and evidence strength per document
**Output**:
- Structured literature review report (.docx / Markdown)
- Literature comparison matrix (.xlsx)
- Sentence-level source annotations

### 3.2 Policy Draft Writing

**Input**: Institutional internal reports, historical policy documents, relevant regulations, current issue descriptions
**Process**:
1. Retrieve policy background, historical evolution, existing proposals related to current issue from knowledge base
2. Generate draft following standard policy document structure (background, problem analysis, proposal recommendations, implementation path, budget assessment)
3. Annotate data sources and references for each key paragraph
**Output**:
- Policy document draft (.docx)
- Citation list
- Briefing PPT (optional)

### 3.3 Policy Option Comparison

**Input**: Multiple policy options to compare (can be documents or structured descriptions)
**Process**:
1. Decompose each option across multiple dimensions: (economic impact, social impact, implementation difficulty, timeline, fiscal cost, risk, evidence support)
2. Retrieve evidence and supporting materials related to each option from knowledge base
3. Generate multi-dimensional comparison analysis, annotating evidence strength (strong/medium/weak/no evidence)
**Output**:
- Policy option comparison analysis report (.docx)
- Multi-dimensional comparison matrix (.xlsx)
- Key differences summary PPT

### 3.4 Technical Material Interpretation

**Input**: Complex technical reports (e.g., environmental impact assessments, macro-econometric model results, industry technical white papers)
**Process**:
1. Parse technical terminology, methodology, data models in technical documents
2. Extract key findings relevant to current policy issues
3. Translate technical language into policy language, annotating imprecision in simplification
**Output**:
- Structured interpretation report (.docx / Markdown)
- Terminology reference table
- Key findings summary PPT

---

## 4. Knowledge Base Design

### 4.1 Dual-Track Knowledge Base Architecture

| Type | Description | Lifecycle |
|------|-------------|-----------|
| **Project KB** | File collections (PDF, Word, Excel, etc.) temporarily imported by analysts for specific tasks | Created with project, archived after project completion |
| **Institutional KB** | Long-term maintained structured document library indexed by topic and type | Continuously updated, reusable across projects |

### 4.2 Supported Document Formats

| Category | Format | Processing Method |
|----------|--------|-------------------|
| Documents | PDF, Word (.docx), Plain Text (.txt), Markdown (.md) | Full-text parsing + structured extraction |
| Data | Excel (.xlsx), CSV | Table parsing + semantic understanding |
| Presentations | PowerPoint (.pptx) | Slide-by-slide parsing |
| Email | .eml | Metadata extraction + body parsing |
| Web Pages | Web archive (.mhtml/.html) | Body extraction + original link retention |
| Scanned | Image PDF/Image files | OCR preprocessing then parsing pipeline |

### 4.3 Knowledge Base Operations

- **Import**: Drag-and-drop upload, folder batch import, API integration
- **Index**: Automatic chunking, embedding vector generation, metadata extraction
- **Search**: Semantic search + keyword search hybrid retrieval, supporting filtering by project/document type/time range
- **Management**: Document version management, expiration marking, permission control

---

## 5. Output & Citation System

### 5.1 Output Formats

- **Markdown**: Structured text, convenient for secondary editing and version management
- **Word (.docx)**: Formal policy documents conforming to GB/T 9704 official document standard, including cover, header, body, footer, etc.
- **Excel (.xlsx)**: Data tables, comparison matrices
- **PowerPoint (.pptx)**: Key findings briefings

### 5.2 Sentence-Level Traceability System

Each LLM-generated assertion based on knowledge base literature must be annotated with:
- Source document name
- Page range / paragraph number
- Relevant original text excerpt (optional display)
- Confidence marker (Direct Citation / Inferred Summary / Cross-Document Synthesis)

**User Interaction**:
- Click any output sentence in the Web interface to expand source details
- Preserve citations as footnotes or endnotes when exporting .docx
- Citations toggleable on/off (Reading Mode / Review Mode)

---

## 6. Permissions & Security

### 6.1 Permission Model

```
Organization
├── Project Group A (KB, analysis results isolated)
│   ├── Analyst A1 (read-write)
│   ├── Analyst A2 (read-write)
│   └── Senior Researcher A3 (read-write+review)
├── Project Group B
│   └── ...
└── System Administrator (global management)
```

### 6.2 Isolation Rules

- Knowledge bases and analysis results between project groups are mutually invisible
- Senior researchers can view all members' work within the group
- Cross-group sharing requires explicit authorization from project administrator
- Institutional KB access permissions can be configured per group

### 6.3 Compliance Requirements

| Standard | Level | Key Requirements | Implementation |
|----------|-------|-----------------|----------------|
| Level 2 Protection | Level 2 | Network security, data security, access control, audit logs | Private deployment, transport encryption, RBAC, operation audit, periodic self-inspection |
| GDPR | Full applicability | Legal basis, data minimization, purpose limitation, right to deletion, data portability, DPIA | User data management features, data export/deletion APIs, data processing agreements, privacy impact assessment, DPO liaison |

#### Level 2 Protection Key Points

- Physical security: Existing physical protection in institutional server rooms
- Network security: Intranet deployment, firewall, TLS transport encryption
- Host security: OS hardening, access control
- Application security: Authentication, RBAC, audit logs, input validation
- Data security: Storage encryption, backup recovery, data integrity verification

#### GDPR Compliance Key Points

- Legal basis for processing: User informed consent + contract performance
- Data subject rights: Provide data access, correction, deletion, export functionality
- Data minimization: Only collect and analyze necessary data
- Cross-border transfer: If using cloud API (Claude), confirm data transfer compliance mechanisms (SCC or equivalent safeguards)
- DPIA (Data Protection Impact Assessment): Complete before system launch
- Processing records: Maintain complete Records of Processing Activities (ROPA)

---

## 7. Technical Architecture

### 7.1 Overall Architecture

```
┌─────────────────────────────────────────────┐
│               Web Frontend (React)           │
├─────────────────────────────────────────────┤
│            API Gateway (FastAPI)              │
├──────┬──────┬──────┬──────┬────────────────┤
│ Doc  │ KB   │ Task │Output│  User/Permission│
│Parse │ Mgmt │Orch  │ Gen  │  Management     │
├──────┴──────┴──────┴──────┴────────────────┤
│              LLM Routing Layer               │
├──────────────────┬─────────────────────────┤
│  Local LLM (Sensitive) │ Cloud API (Non-sensitive) │
├──────────────────┴─────────────────────────┤
│        Vector DB + Document Storage          │
└─────────────────────────────────────────────┘
```

### 7.2 Key Modules

| Module | Function |
|--------|----------|
| Document Parsing Engine | Multi-format parsing, OCR, structured extraction, chunking |
| Knowledge Base Management | Vector indexing, metadata management, search ranking |
| LLM Routing | Route to local or cloud models by task sensitivity |
| Task Orchestration | Multi-step analysis workflow (Retrieve → Generate → Citation Verify → Format) |
| Output Generation | Sentence-level traceability annotation, multi-format export |
| Permission Management | RBAC, project group isolation, audit logs |

### 7.3 LLM Hybrid Deployment

> **Important Note**: Anthropic Claude is the currently confirmed cloud LLM. Claude does not support local private deployment, so sensitive data local inference requires other privately deployable models. Below is the hybrid deployment plan:

| Data Type | Deployment Location | Model | Notes |
|-----------|-------------------|-------|-------|
| Internal reports, policy documents, sensitive data | Local GPU cluster | Qwen / DeepSeek / Llama (to be evaluated and selected) | Deployed on existing institutional GPU cluster, data stays within intranet |
| Public literature, non-sensitive tasks | Cloud API | **Claude API** (confirmed) | Leverage Claude's analytical reasoning for non-sensitive tasks |
| Final review, sensitive context | Local GPU cluster | Same as local model | Review strictly executed locally |

**Local Model Selection Recommendations** (to be confirmed after evaluation on actual GPU hardware):
1. **Qwen3**: Domestic model, strong Chinese policy text understanding, good compliance
2. **DeepSeek-V3**: Strong comprehensive capability, low inference cost, excellent Chinese performance
3. **Llama 4 + Chinese fine-tuning**: Mature open-source ecosystem, comprehensive deployment toolchain

Routing Rules:
- Auto-judgment on new analysis task creation: public knowledge sources only → Claude API; involving internal documents → local model
- Users can manually specify model for individual tasks
- Administrators can configure default routing policy and sensitivity threshold

### 7.4 Technology Selection

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | **React + TypeScript** (confirmed) | Web interface, responsive design, enterprise component library |
| Backend | Python + FastAPI | High-performance async API |
| Database | PostgreSQL | Business data storage |
| Vector DB | Milvus / Qdrant | KB vector retrieval, supporting 50K+ document scale |
| Document Storage | MinIO / Local filesystem | Original document storage |
| Document Parsing | Unstructured + custom adapters | Multi-format parsing |
| OCR | **Tesseract + Chinese language pack** (confirmed) | Open-source OCR, low cost and supports privatization |
| Local LLM | vLLM / Ollama | Local model inference service, leveraging existing GPU cluster |
| Cloud LLM | **Anthropic Claude API** (confirmed) | Primary analysis engine for non-sensitive tasks |
| Task Queue | Celery + Redis | Async long-running task processing |
| Monitoring | Prometheus + Grafana | System operation monitoring |

### 7.5 Infrastructure

- **GPU Cluster**: Existing institutional, directly usable for local LLM inference deployment
- **Storage**: 50K+ documents original storage + vector index, estimated total storage ~5-10 TB
- **Network**: Intranet deployment, external Web access via reverse proxy

---

## 8. MVP Scope & Delivery Plan

### 8.1 MVP Scope (1-2 months rapid prototype)

| Priority | Feature | Notes |
|----------|---------|-------|
| P0 | Web basic framework | User login, project management, basic interface |
| P0 | Document import & parsing | PDF, Word, plain text import and full-text parsing |
| P0 | Literature review workflow | Core feature, end-to-end usable |
| P0 | Policy draft writing workflow | Core feature, end-to-end usable |
| P0 | Basic knowledge base | Project KB creation, indexing, retrieval |
| P0 | Markdown + .docx export | Two core output formats |
| P0 | Paragraph-level source annotation | MVP at paragraph level, sentence level in subsequent iterations |
| P1 | Policy option comparison workflow | Core feature |
| P1 | Technical material interpretation workflow | Core feature |
| P1 | .xlsx + .pptx export | Supplementary output formats |
| P1 | Basic permissions (roles + project group isolation) | Basic requirement for institutional deployment |
| P2 | Institutional KB | Long-term KB management |
| P2 | OCR support | Scanned document processing |
| P2 | Cloud LLM integration | Hybrid deployment |
| P2 | Result sharing | Intra-group sharing |
| P3 | Email/web archive parsing | Supplementary formats |
| P3 | Advanced search filtering | Multi-dimensional search |

### 8.2 Suggested Iteration Cadence

| Phase | Period | Goal |
|-------|--------|------|
| Sprint 1-2 | Weeks 1-4 | Basic framework + document parsing + literature review workflow |
| Sprint 3-4 | Weeks 5-8 | Policy draft + policy comparison + technical interpretation + permissions + multi-format export |
| Post-MVP | Month 3+ | Institutional KB, OCR, cloud integration, result sharing, supplementary formats |

---

## 9. Non-Functional Requirements

### 9.1 Performance

- Single document parse time < 30 seconds (50-page PDF reference)
- Analysis task response time < 3 minutes (typical literature review, 10 documents)
- Web interface first screen load < 3 seconds
- KB supports 50K+ document indexing and retrieval, search latency < 2 seconds
- Concurrent users: < 20 analysts online simultaneously, peak task queue depth 50

### 9.2 Availability

- System availability > 99% (private deployment, institutional O&M guaranteed)
- Long tasks executed asynchronously, supporting progress display and failure retry
- Complete auditable operation logs

### 9.3 Security (Level 2 Protection + GDPR)

- Full-chain TLS 1.2+ encrypted data transmission
- AES-256 encrypted static data storage
- Complete identity authentication (supporting LDAP/SSO integration with institutional account system)
- RBAC fine-grained access control
- API rate limiting
- All operation audit logs retained no less than 6 months
- Sensitive data marking and auto-routing: internal/sensitive knowledge sources auto-routed to local LLM
- GDPR data subject rights: provide data access, correction, deletion, export functionality

---

## 10. Key Decision Summary

Below are decisions already finalized during the requirements confirmation process, serving as the baseline for development startup:

| # | Decision Item | Conclusion | Impact Scope |
|---|--------------|-----------|--------------|
| 1 | Cloud LLM | **Anthropic Claude API** (confirmed) | Primary engine for non-sensitive tasks |
| 2 | Local LLM | Qwen/DeepSeek/Llama candidates, to be evaluated on existing GPU cluster | Sensitive data processing, review |
| 3 | KB Scale | **Large**: 50K+ existing documents, vector DB needs 100K-level capacity planning | Vector DB selection, storage planning |
| 4 | Concurrent Users | **Small**: < 20 analysts simultaneously online | API capacity, task queue design |
| 5 | Report Format | **GB/T 9704 Official Document Standard** | .docx generation template, typesetting engine |
| 6 | Frontend Framework | **React + TypeScript** (confirmed) | Frontend tech selection, component library choice |
| 7 | Infrastructure | **Existing GPU cluster**, private intranet deployment | Can immediately begin local LLM evaluation |
| 8 | OCR Engine | **Tesseract + Chinese language pack** (confirmed) | Document parsing pipeline, scanned document processing |
| 9 | Protection Level | **Level 2** | Security architecture design, audit requirements |
| 10 | GDPR | **Full applicability**, complete compliance required | Data processing flow, DPIA, cross-border transfer mechanism |

### Items Still Requiring Confirmation

The following items need confirmation from stakeholders before Sprint 1 starts, but have recommended approaches:

| # | Item | Recommended Approach | Confirming Party |
|---|------|---------------------|------------------|
| A | Local LLM final selection | Evaluate Qwen3 / DeepSeek-V3 / Llama 4 on existing GPU cluster for Chinese policy text | Tech team |
| B | GPU cluster specs & available compute | Submit compute requirements list (estimated 2×A100 or equivalent) | IT Operations |
| C | Institutional .docx template | Provide existing GB/T 9704 template file or specification document | Institutional Office/Admin |
| D | LDAP/SSO account integration | Confirm institutional identity system type and interface specifications | IT Operations |
| E | Claude API GDPR cross-border compliance | Confirm SCC or equivalent mechanisms meet compliance requirements | Legal/DPO |
| F | First batch KB document list | Confirm institutional KB document scope and access permissions for MVP | Business lead |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| Knowledge Base | Structured document collection supporting LLM Retrieval-Augmented Generation (RAG) |
| Project Group | Work isolation unit within the organization; a group has its own independent KB and analysis results |
| Sentence-Level Traceability | Associating each evidence-based assertion in output text with specific source document location |
| Hybrid LLM Deployment | Using both locally deployed models and cloud API models simultaneously, routing by data sensitivity |
| Vector Retrieval | Semantic similarity-based document retrieval, core technical component of RAG |

---

## Appendix B: UI Concept Mockup

### Main Workspace

```
┌─────────────────────────────────────────────────────┐
│  PolicyAI                      [Project▾] [User▾]     │
├──────────┬──────────────────────────────────────────┤
│          │                                          │
│  📁 Projects│  Current Task: Literature Review        │
│  ├ KB     │  ┌─────────────────────────────────────┐│
│  ├ Tasks  │  │ Status: Retrieved → Generating...    ││
│  └ Output │  │ Progress: ████████░░░░  67%         ││
│          │  └─────────────────────────────────────┘│
│  📋 Tasks:│                                          │
│  □ Lit Rev│  Output Preview:                         │
│  ■ Policy │  ┌─────────────────────────────────────┐│
│  □ Compare│  │ 1. Research Background & Problem     ││
│  □ Tech   │  │                                     ││
│          │  │ Recently, digital trade rules have... ││
│          │  │ [1] WTO(2023) p.45-48               ││
│          │  └─────────────────────────────────────┘│
│          │  [Export .docx] [Export .md] [Review Mode]│
└──────────┴──────────────────────────────────────────┘
```

### Sentence-Level Traceability Interaction

```
Click [1] annotation in output:
┌─────────────────────────────────────────────┐
│ Source Details                       [✕]    │
│                                             │
│ 📄 WTO World Trade Report 2023               │
│ 📍 Pages 45-48, Section 3.2                  │
│ 📝 "Digital trade rules have increasingly    │
│    become a central component of..."         │
│                                             │
│ Confidence: Direct Citation                  │
│ [Jump to Original Document]                  │
└─────────────────────────────────────────────┘
```

---

*Document version: v2.0 (Final) | Date: 2026-05-17 | Status: Confirmed, ready for development*
