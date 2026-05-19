import { Upload, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';

const { Dragger } = Upload;

const ALLOWED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
  'text/csv',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-powerpoint',
  'text/markdown',
  'text/plain',
  'text/html',
  'message/rfc822',
];

const ALLOWED_EXTENSIONS = [
  '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv',
  '.pptx', '.ppt', '.md', '.txt', '.html', '.eml',
];

const MAX_FILE_SIZE_MB = 100;

interface DocumentUploadProps {
  projectId: string;
  onUpload: (file: File, isInternal: boolean) => Promise<void>;
}

export default function DocumentUpload({
  onUpload,
}: DocumentUploadProps) {
  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess, onError } = options;
    const uploadFile = file as File;

    // Validate file size
    if (uploadFile.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      message.error(`文件大小超过限制（${MAX_FILE_SIZE_MB}MB）`);
      onError?.(new Error('File too large'));
      return;
    }

    // Validate file type
    const ext = '.' + uploadFile.name.split('.').pop()?.toLowerCase();
    if (
      !ALLOWED_TYPES.includes(uploadFile.type) &&
      !ALLOWED_EXTENSIONS.includes(ext)
    ) {
      message.error(`不支持的文件格式：${ext}`);
      onError?.(new Error('Unsupported format'));
      return;
    }

    try {
      await onUpload(uploadFile, false);
      onSuccess?.(uploadFile);
      message.success(`${uploadFile.name} 上传成功`);
    } catch (error) {
      message.error(`${uploadFile.name} 上传失败`);
      onError?.(error as Error);
    }
  };

  return (
    <Dragger
      customRequest={handleUpload}
      multiple
      showUploadList={{
        showDownloadIcon: false,
        showPreviewIcon: true,
        showRemoveIcon: true,
      }}
      accept={ALLOWED_EXTENSIONS.join(',')}
    >
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
      <p className="ant-upload-hint">
        支持 PDF、Word、Excel、PPT、Markdown、TXT、HTML 格式，单文件不超过 {MAX_FILE_SIZE_MB}MB
      </p>
    </Dragger>
  );
}