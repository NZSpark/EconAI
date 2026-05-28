import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import DocumentUpload from '../../components/DocumentUpload';

const { mockMessage } = vi.hoisted(() => ({
  mockMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return { ...actual, message: mockMessage };
});

// Helper to create a mock File
function createFile(name: string, size: number, type: string): File {
  const content = new Array(size).fill('a').join('');
  return new File([content], name, { type });
}

// Helper: fire a file input change event
function uploadFile(fileOrFiles: File | File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  if (!input) throw new Error('File input not found in DOM');

  const dt = new DataTransfer();
  const files = Array.isArray(fileOrFiles) ? fileOrFiles : [fileOrFiles];
  files.forEach((f) => dt.items.add(f));
  // eslint-disable-next-line no-param-reassign
  input.files = dt.files;
  fireEvent.change(input);
}

describe('DocumentUpload Component', () => {
  let onUpload: ReturnType<typeof vi.fn>;
  let onDone: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    onUpload = vi.fn().mockResolvedValue(undefined);
    onDone = vi.fn();
  });

  function renderComponent() {
    return render(
      <DocumentUpload projectId="test-project" onUpload={onUpload} onDone={onDone} />
    );
  }

  // ---- Static content ----

  it('should render the upload area with instructions', () => {
    renderComponent();
    expect(screen.getByText('点击或拖拽文件到此区域上传')).toBeInTheDocument();
    expect(
      screen.getByText(/支持 PDF、Word、Excel、PPT、Markdown、TXT、HTML 格式，单文件不超过 100MB/)
    ).toBeInTheDocument();
  });

  // ---- File validation: oversized ----

  it('should reject files larger than 100MB', async () => {
    renderComponent();
    const largeFile = createFile('big.pdf', 101 * 1024 * 1024, 'application/pdf');
    uploadFile(largeFile);

    await waitFor(() => {
      expect(mockMessage.error).toHaveBeenCalledWith(
        expect.stringContaining('文件大小超过限制')
      );
    });
    expect(onUpload).not.toHaveBeenCalled();
  });

  // ---- File validation: unsupported format ----

  it('should reject unsupported file formats', async () => {
    renderComponent();
    const badFile = createFile('photo.jpg', 1024, 'image/jpeg');
    uploadFile(badFile);

    await waitFor(() => {
      expect(mockMessage.error).toHaveBeenCalledWith(
        expect.stringContaining('不支持的文件格式')
      );
    });
    expect(onUpload).not.toHaveBeenCalled();
  });

  // ---- Successful upload: PDF ----

  it('should call onUpload with file, isInternal=false, and onProgress callback', async () => {
    renderComponent();
    const pdfFile = createFile('report.pdf', 1024 * 1024, 'application/pdf');
    uploadFile(pdfFile);

    await waitFor(() => {
      expect(onUpload).toHaveBeenCalledTimes(1);
    });
    const callArgs = onUpload.mock.calls[0];
    expect(callArgs[0].name).toBe('report.pdf');
    expect(callArgs[1]).toBe(false);
    expect(typeof callArgs[2]).toBe('function');
  });

  // ---- onDone callback ----

  it('should call onDone after successful upload', async () => {
    renderComponent();
    const pdfFile = createFile('report.pdf', 1024, 'application/pdf');
    uploadFile(pdfFile);

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledTimes(1);
    });
  });

  it('should NOT call onDone after failed upload + show error message', async () => {
    onUpload.mockRejectedValue(new Error('Upload failed'));

    renderComponent();
    const pdfFile = createFile('fail.pdf', 1024, 'application/pdf');
    uploadFile(pdfFile);

    await waitFor(() => {
      expect(onUpload).toHaveBeenCalledTimes(1);
    });
    expect(onDone).not.toHaveBeenCalled();
    expect(mockMessage.error).toHaveBeenCalledWith(
      expect.stringContaining('上传失败')
    );
  });

  // ---- Success message ----

  it('should show success message after upload', async () => {
    renderComponent();
    const pdfFile = createFile('report.pdf', 1024, 'application/pdf');
    uploadFile(pdfFile);

    await waitFor(() => {
      expect(mockMessage.success).toHaveBeenCalledWith(
        expect.stringContaining('上传成功')
      );
    });
  });

  // ---- Extension-based validation (.md without proper MIME) ----

  it('should accept .md extension even without text/markdown MIME type', async () => {
    renderComponent();
    const mdFile = createFile('README.md', 512, '');
    uploadFile(mdFile);

    await waitFor(() => {
      expect(onUpload).toHaveBeenCalledTimes(1);
    });
  });

  // ---- Multiple files ----

  it('should handle multiple file uploads sequentially', async () => {
    renderComponent();
    const files = [
      createFile('a.pdf', 1024, 'application/pdf'),
      createFile('b.docx', 2048, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    ];
    uploadFile(files);

    await waitFor(() => {
      expect(onUpload).toHaveBeenCalledTimes(2);
    });
    expect(onDone).toHaveBeenCalledTimes(2);
  });
});
