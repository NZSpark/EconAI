# EconAI User Manual

> Version: v1.3 | For EconAI v1.3

---

## 1. System Overview

EconAI is an AI-driven economic policy analysis toolkit. You can upload policy literature, research reports, and other documents. The system automatically completes analysis tasks such as literature reviews, policy drafts, policy comparisons, and technical interpretations, producing professional reports with **sentence-level source traceability**.

### Core Features

| Feature | Description |
|---------|-------------|
| Literature Review | Automatically generate structured literature review reports based on uploaded documents |
| Policy Draft | Automatically draft policy documents based on background information |
| Policy Comparison | Cross-comparison analysis of multiple policy documents |
| Technical Interpretation | Clause-by-clause interpretation and compliance analysis of technical standards/regulations |

### Citation Traceability

All AI-generated reports carry **sentence-level citation annotations** traceable to specific paragraphs and pages in original documents. Citations fall into three confidence levels:

| Color | Confidence | Meaning |
|-------|-----------|---------|
| Green | Direct Citation | High confidence, content closely matches source |
| Yellow | Fuzzy Citation | Medium confidence, semantically related but not directly corresponding |
| Red | Uncertain | Low confidence, inferential content |

---

## 2. Logging In

### 2.1 Open the System

Access the link provided by your system administrator in a browser (e.g., `https://econai.your-institution.cn`).

### 2.2 Login

1. Enter your **username** and **password**
2. Click the "Login" button

For first-time login, use the account assigned by your administrator. Default admin account:
- Username: `admin`
- Password: `Admin@123456` (change after first login)

After successful login, you will be automatically redirected to the project list page.

### 2.3 Logout

Click your avatar in the top-right corner → Select "Logout".

---

## 3. Project Management

### 3.1 View Project List

After login, you will see the **Project List** page showing all projects you have permission to view.

- **Search**: Enter a project name in the search box and press Enter or click "Search"
- **Status Filter**: Toggle between "Active" / "Archived" to view projects in different states
- **Pagination**: Use the pagination controls at the bottom to browse

### 3.2 Create Project

1. Click the "Create Project" button in the top-right corner
2. Fill in the form:
   - **Project Name**: e.g., "2024 Digital Trade Policy Research"
   - **Description**: Brief description of project background and objectives (optional)
   - **Project Group**: Enter the project group ID
3. Click "Create"

### 3.3 Enter a Project

Click the project name or "View" button to enter the project details page. The project details page contains two sub-pages:

- **Knowledge Base**: Manage project documents
- **Tasks**: Manage analysis tasks

### 3.4 Archive Project

For projects no longer active, click the "Archive" button. After archiving, the project becomes read-only and no longer appears in the default list.

---

## 4. Knowledge Base Management

The Knowledge Base is your project's "library" — all uploaded documents are parsed, chunked, and indexed here for AI analysis retrieval.

### 4.1 Upload Documents

In the "Knowledge Base" tab of the project details page:

1. **Drag & Drop Upload**: Drag document files into the upload area
2. Or click the upload area to select files
3. Supported file formats:

| Format | Extensions |
|--------|-----------|
| PDF | `.pdf` |
| Word | `.docx`, `.doc` |
| Excel/CSV | `.xlsx`, `.xls`, `.csv` |
| PowerPoint | `.pptx`, `.ppt` |
| Markdown/Text | `.md`, `.txt` |
| Email | `.eml` |
| Web Pages | `.html`, `.htm`, `.mhtml`, `.mht` |
| Images (OCR) | `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp` (text content auto-recognized) |

- Max file size: 100MB per file
- Upload shows a progress bar, parsing starts automatically after completion

> **OCR Image Recognition**: The system not only supports standalone image files but also automatically extracts embedded images from PDF, DOCX, PPTX, and HTML documents, performs OCR on the text in images, and merges recognized text into the document's text content.

### 4.2 View Document List

The document list shows all uploaded documents including:
- Filename, format, file size
- Parse status: `pending`, `parsing`, `ready`, `error`
- Action buttons: **Download** (download original file), **Details**, **Re-index**, **Delete**

Documents can be filtered by status.

### 4.3 Download Documents

Click the **Download** button in the "Actions" column of the document list, and the browser will automatically download the original file.

### 4.4 View Document Details

Click a document row to view the details panel:
- Metadata (title, author, date, source, page count, etc.)
- Parse status details
- If parsing failed, click "Re-index" to retry

### 4.5 Delete Documents

Click the "Delete" button at the end of a document row, confirm, and the document and all associated data will be cascade-deleted.

### 4.6 Search Knowledge Base

Enter keywords in the search box for hybrid search (semantic matching + keyword matching):
- Results list shows matching text fragments
- Each result is annotated with **source document full filename** (including extension, e.g., "ENG60459511 - Approved Engineering Plan.pdf") and relevance score
- Matching keywords are highlighted

---

## 5. Analysis Tasks

### 5.1 Create Task

In the "Tasks" tab of the project details page:

1. Click the "Create Task" button
2. Select task type:

| Type | Purpose | Use Case |
|------|---------|----------|
| Literature Review | Systematic review and summary of existing literature | Research background survey |
| Policy Draft | Draft policy documents | Policy formulation |
| Policy Comparison | Cross-comparison analysis of different policy documents | Policy evaluation |
| Technical Interpretation | Interpretation of technical standards/regulations | Compliance analysis |

3. Fill in the task form:
   - **Title**: Task name, e.g., "Digital Trade Barriers Literature Review"
   - **Description**: Detailed description and requirements of the task
   - **Knowledge Sources**: Select which documents to use as analysis basis
   - **Output Format**: Select report output format (docx/md/xlsx/pptx)
   - **Analysis Parameters**: Configure specific parameters based on task type
4. Click "Submit" to start analysis

### 5.2 View Task List

The task list shows all analysis tasks including:

- Task title
- Task type (Literature Review / Policy Draft / Policy Comparison / Technical Interpretation)
- Status: `pending`, `running`, `completed`, `failed`, `cancelled`
- Progress information
- Creation time

Tasks can be filtered by status or browsed with pagination.

### 5.3 Monitor Task Progress

After creating a task, the system automatically starts analysis. Task progress is displayed in real-time:

1. **Step Progress Bar**: Shows the current execution step
   - Plan → Retrieve → Generate → Verify → Format → Export
2. **Current Step Description**: Shows the specific operation being performed
3. **Estimated Remaining Time**: Estimated based on steps

Progress auto-refreshes every 3 seconds, and polling stops automatically when the task completes.

### 5.4 Task Failure Handling

If a task fails, the page displays an error message. You can:
- View detailed error reason
- Click "Retry" to re-execute the task

---

## 6. Viewing Analysis Results

After task completion, you are automatically taken to the **Output page**.

### 6.1 Preview Report

Report content is displayed in **Markdown Preview** mode by default:
- Section titles, body text, and tables are fully rendered
- Citation badges `[1]`, `[2]`, etc. are clickable for details

Click the "Raw" tab to switch to Markdown source view.

### 6.2 View Citation Sources

Click citation badges in the report to open a **Citation Detail Popover** showing:

- Confidence label (Green/Yellow/Red)
- Source document name
- Page range
- Original text excerpt
- AI-generated citation sentence

### 6.3 Citation List Panel

Click the "Citation List" button to open the side panel:

- Filter by confidence: All / Direct Citation / Fuzzy Citation / Uncertain
- Each citation card shows detailed information
- Top bar shows citation statistics (total count, count per confidence level)

### 6.4 Export Reports

Select the export format at the top of the output page, then click "Export":

| Format | Description |
|--------|-------------|
| Markdown (.md) | Text format, suitable for further editing |
| Word (.docx) | GB/T 9704 official document format, with full layout |
| Excel (.xlsx) | Comparison analysis table + citation list |
| PPT (.pptx) | Presentation format |

The browser will automatically download the exported file with Chinese filename support.

---

## 7. Admin Features (Administrators)

Administrators can access backend management features. Click the "Admin" menu in the sidebar.

### 7.1 User Management

Path: `/admin/users`

- **View User List**: Shows all registered users
- **Create User**: Click "Create User", fill in username, email, password, and role
- **Edit User**: Modify user information or role
- **Deactivate/Activate User**: Toggle user account status

System Roles:

| Role | Permissions |
|------|------------|
| Analyst | View projects, create tasks, view outputs |
| Senior Researcher | Analyst permissions + create projects, manage knowledge base |
| Project Admin | Senior Researcher permissions + manage project group members |
| System Admin | All permissions + user management, audit logs |

### 7.2 Project Group Management

Path: `/admin/groups`

- **View Group List**: Shows all project groups with member counts
- **Create Group**: Fill in name and description
- **Manage Members**: Click "Manage Members" button to open dialog
  - **Member List**: Table showing each member's **username**, **display name**, **role**
  - **Add Member**: **Enter username or display name** in the search box for fuzzy search, select from dropdown, then click "Add Member"
  - **Remove Member**: Click "Remove" on the right side of the table, confirm to remove
- The search box only lists active users **not yet in the group** to avoid duplicates

Projects are mounted under project groups; users can access all projects in their group.

### 7.3 Audit Logs

Path: `/admin/audit-logs`

- View all operation records in the system
- Filter by **time range**
- Filter by **operator**
- Filter by **operation type** (Create/Modify/Delete/View)
- Paginated browsing of history

Log content: operator, operation time, operation type, target resource, operation details.

---

## 8. Typical Workflows

### Scenario 1: Writing a Literature Review

1. **Create Project**: New project "2024 Digital Trade Policy Research"
2. **Upload Literature**: Drag relevant PDF/Word documents into the knowledge base upload area
3. **Wait for Parsing**: Wait for document status to become "ready" (typically 1-2 minutes)
4. **Create Task**: Select "Literature Review" type, set analysis scope
5. **Wait for Analysis**: System automatically retrieves, generates, and verifies citations (typically 5-10 minutes)
6. **View Report**: Inspect the automatically generated structured review
7. **Review Citations**: Check the source reliability of each argument via the citation list
8. **Export**: Export as Word document or Markdown text

### Scenario 2: Policy Comparison Analysis

1. **Upload Two Policy Documents** to the knowledge base
2. **Create Task**: Select "Policy Comparison" type
3. **Select Comparison Dimensions**: Specify dimensions of interest in task parameters
4. **Wait for Analysis to Complete**
5. **View Comparison Matrix**: System generates multi-dimensional comparison table
6. **Export Excel**: Export as .xlsx for comparison analysis report

---

## 9. FAQ

### Document Shows "Parsing" for a Long Time After Upload

- Larger PDF documents take longer to parse
- Documents with many embedded images (e.g., PPTX, image-heavy PDFs) require additional OCR, which may take longer
- Image-only PDFs require full-page OCR, which may take longer
- If exceeding 10 minutes, try deleting and re-uploading

### Task Execution Failed

Common causes:
- Claude API key not configured or quota exhausted (contact administrator)
- Claude API custom endpoint misconfigured (Docker's `localhost` must be changed to `host.docker.internal`)
- Knowledge base lacks relevant documents (upload documents before creating tasks)
- Task timeout (large projects may need more processing time; retrying usually resolves)

### Citations Showing "Uncertain"

- Indicates the AI-generated sentence could not find a corresponding match in the source text
- Check the reasonableness of the sentence and manually modify if needed
- Use "Citation List" to filter and view all low-confidence citations

### Forgot Password

Contact your system administrator for a password reset. Self-service password reset is not currently supported.

---

## Quick Reference

| Operation | Steps |
|-----------|-------|
| Create Project | Project List → Create Project → Fill info → Confirm |
| Upload Document | Enter Project → Knowledge Base → Drag & Drop |
| Literature Review | Create Task → Literature Review → Set Parameters → Submit |
| Policy Draft | Create Task → Policy Draft → Set Parameters → Submit |
| Policy Comparison | Create Task → Policy Comparison → Set Parameters → Submit |
| Technical Interpretation | Create Task → Technical Interpretation → Set Parameters → Submit |
| View Citation | Click `[1]` etc. badges in report → View popover panel |
| Export Report | Output Page → Select Format → Click Export |
| Manage Users | Admin → User Management → Create/Edit/Deactivate |
| Audit Logs | Admin → Audit Logs → Filter & View |
