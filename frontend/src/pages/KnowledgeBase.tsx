import { useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Card,
  Table,
  Button,
  Input,
  Select,
  Space,
  Tag,
  Drawer,
  Modal,
  Popconfirm,
  Empty,
  message,
  Typography,
  Descriptions,
  List,
} from 'antd';
import {
  UploadOutlined,
  SearchOutlined,
  ReloadOutlined,
  DeleteOutlined,
  EyeOutlined,
  RedoOutlined,
  FileTextOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../hooks/useRequest';
import { listDocuments, uploadDocument, deleteDocument, reindexDocument, getDocument, getDocumentContent, downloadDocumentFile } from '../api/documents';
import type { DocumentContent } from '../api/documents';
import { searchProjectKB } from '../api/search';
import DocumentUpload from '../components/DocumentUpload';
import type { DocumentItem, SearchResultChunk } from '../api/types';
import { parseStatusColorMap, parseStatusLabelMap, formatColorMap } from '../constants/labels';
import { formatFileSize, formatDate } from '../utils/format';

const { Title, Text } = Typography;

export default function KnowledgeBase() {
  const { id: projectId } = useParams<{ id: string }>();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [uploadDrawerOpen, setUploadDrawerOpen] = useState(false);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [contentModalOpen, setContentModalOpen] = useState(false);
  const [contentData, setContentData] = useState<DocumentContent | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [reindexingDocs, setReindexingDocs] = useState<Set<string>>(new Set());

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResultChunk[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchTime, setSearchTime] = useState(0);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchPage, setSearchPage] = useState(1);
  const [searchPageSize, setSearchPageSize] = useState(10);
  const [searchPages, setSearchPages] = useState(1);

  const loadDocs = useCallback(async () => {
    if (!projectId) throw new Error('No project ID');
    return listDocuments(projectId, {
      page,
      page_size: pageSize,
      status: statusFilter,
    });
  }, [projectId, page, pageSize, statusFilter]);

  const { data, loading, error, run: refresh } = useRequest(loadDocs, { refreshDeps: [page, pageSize] });

  const handleUpload = async (
    file: File,
    isInternal: boolean,
    onProgress?: (percent: number) => void
  ) => {
    if (!projectId) return;
    await uploadDocument(projectId, file, isInternal, undefined, onProgress);
    await refresh();
  };

  const handleDelete = async (docId: string) => {
    if (!projectId) return;
    try {
      await deleteDocument(projectId, docId);
      message.success('文档已删除');
      refresh();
    } catch {
      message.error('删除失败');
    }
  };

  const handleReindex = async (docId: string) => {
    if (!projectId) return;
    setReindexingDocs((prev) => new Set(prev).add(docId));
    try {
      await reindexDocument(projectId, docId);
      message.success('已触发重新索引');
      refresh();
      // 轮询直到文档状态回到 ready
      await pollUntilReady(docId);
    } catch {
      message.error('重新索引失败');
    } finally {
      setReindexingDocs((prev) => {
        const next = new Set(prev);
        next.delete(docId);
        return next;
      });
    }
  };

  // 轮询文档状态，直到 ready 或 error 后自动刷新列表
  const pollUntilReady = async (docId: string) => {
    if (!projectId) return;
    for (let i = 0; i < 30; i++) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      try {
        const doc = await getDocument(projectId, docId);
        if (doc.parse_status === 'ready' || doc.parse_status === 'error') {
          break;
        }
      } catch {
        break;
      }
    }
    refresh();
  };

  const handleViewDetail = async (doc: DocumentItem) => {
    if (!projectId) return;
    try {
      const detail = await getDocument(projectId, doc.document_id);
      setSelectedDoc(detail);
      setDetailDrawerOpen(true);
    } catch {
      message.error('获取文档详情失败');
    }
  };

  const handleViewContent = async (doc: DocumentItem) => {
    if (!projectId) return;
    setLoadingContent(true);
    try {
      const content = await getDocumentContent(projectId, doc.document_id);
      setContentData(content);
      setContentModalOpen(true);
    } catch {
      message.error('获取文档内容失败');
    } finally {
      setLoadingContent(false);
    }
  };

  const handleSearch = async (page = 1) => {
    if (!projectId || !searchQuery.trim()) return;
    setSearching(true);
    setSearchPage(page);
    try {
      const res = await searchProjectKB(projectId, {
        query: searchQuery,
        top_k: 100,
        page,
        page_size: searchPageSize,
      });
      setSearchResults(res.results);
      setSearchTotal(res.total_hits);
      setSearchTime(res.search_time_ms);
      setSearchPages(res.pages);
      setHasSearched(true);
    } catch {
      message.error('搜索失败');
    } finally {
      setSearching(false);
    }
  };

  const columns: ColumnsType<DocumentItem> = [
    {
      title: '文件名',
      dataIndex: 'original_name',
      key: 'original_name',
      ellipsis: true,
    },
    {
      title: '格式',
      dataIndex: 'format',
      key: 'format',
      width: 80,
      render: (fmt: string) => (
        <Tag color={formatColorMap[fmt] || 'default'}>{fmt.toUpperCase()}</Tag>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      key: 'size_bytes',
      width: 100,
      render: (size: number) => formatFileSize(size),
    },
    {
      title: '解析状态',
      dataIndex: 'parse_status',
      key: 'parse_status',
      width: 100,
      render: (status: string) => (
        <Tag color={parseStatusColorMap[status]}>
          {parseStatusLabelMap[status] || status}
        </Tag>
      ),
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => formatDate(text),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, record: DocumentItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => {
              downloadDocumentFile(projectId || '', record.document_id, record.original_name).catch(() => {
                message.error('下载失败');
              });
            }}
          >
            下载
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record)}
          >
            详情
          </Button>
          {(record.parse_status === 'ready' || record.parse_status === 'parsing') && (
            <>
              <Button
                type="link"
                size="small"
                icon={<FileTextOutlined />}
                loading={loadingContent}
                onClick={() => handleViewContent(record)}
              >
                内容
              </Button>
              <Button
                type="link"
                size="small"
                icon={<RedoOutlined />}
                loading={reindexingDocs.has(record.document_id)}
                disabled={reindexingDocs.has(record.document_id) || record.parse_status === 'parsing'}
                onClick={() => handleReindex(record.document_id)}
              >
                重索引
              </Button>
            </>
          )}
          <Popconfirm
            title="确认删除"
            description="删除后将级联删除所有相关数据，无法恢复"
            onConfirm={() => handleDelete(record.document_id)}
            okText="确认"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={5} style={{ margin: 0 }}>
          文档列表
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<UploadOutlined />}
            onClick={() => setUploadDrawerOpen(true)}
          >
            上传文档
          </Button>
        </Space>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="状态筛选"
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v);
            setPage(1);
          }}
          allowClear
          style={{ width: 140 }}
          options={[
            { label: '全部', value: undefined },
            { label: '等待中', value: 'pending' },
            { label: '解析中', value: 'parsing' },
            { label: '就绪', value: 'ready' },
            { label: '解析失败', value: 'error' },
          ]}
        />
      </Space>

      {error && (
        <div style={{ marginBottom: 16, color: '#ff4d4f' }}>
          加载失败：{error.message || '未知错误'}
        </div>
      )}

      <Table<DocumentItem>
        columns={columns}
        dataSource={data?.items || []}
        rowKey="document_id"
        loading={loading}
        locale={{
          emptyText: <Empty description="暂无文档，请上传" />,
        }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total || 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个文档`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      {/* KB Search Section */}
      <Card
        title="知识库搜索"
        style={{ marginTop: 24 }}
        extra={
          <Text type="secondary">
            {hasSearched ? `找到 ${searchTotal} 条结果，耗时 ${searchTime}ms` : ''}
          </Text>
        }
      >
        <Space style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="输入搜索关键词..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onSearch={() => handleSearch(1)}
            onPressEnter={() => handleSearch(1)}
            loading={searching}
            style={{ width: 400 }}
            prefix={<SearchOutlined />}
            allowClear
          />
        </Space>

        {hasSearched && searchResults.length === 0 && (
          <Empty description="未找到相关结果" />
        )}

        {hasSearched && searchResults.length > 0 && (
          <List
            dataSource={searchResults}
            pagination={{
              current: searchPage,
              pageSize: searchPageSize,
              total: searchTotal,
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50'],
              showTotal: (total, range) =>
                `第 ${range[0]}-${range[1]} 条，共 ${total} 条`,
              onChange: (p, ps) => {
                setSearchPageSize(ps);
                handleSearch(p);
              },
            }}
            renderItem={(item: SearchResultChunk) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{item.document_title}</Text>
                      <Tag color="blue">{(item.score * 100).toFixed(1)}%</Tag>
                    </Space>
                  }
                  description={
                    <div>
                      <Text>
                        {item.highlighted_content ? (
                          <span dangerouslySetInnerHTML={{ __html: item.highlighted_content }} />
                        ) : (
                          item.content
                        )}
                      </Text>
                      <div style={{ marginTop: 4 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          页码：{item.metadata.page_start}-{item.metadata.page_end}
                          {item.metadata.section_title &&
                            ` | 章节：${item.metadata.section_title}`}
                        </Text>
                      </div>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* Upload Drawer */}
      <Drawer
        title="上传文档"
        open={uploadDrawerOpen}
        onClose={() => setUploadDrawerOpen(false)}
        width={480}
      >
        <DocumentUpload
          key={String(uploadDrawerOpen)}
          projectId={projectId || ''}
          onUpload={async (file, isInternal, onProgress) => {
            await handleUpload(file, isInternal, onProgress);
          }}
          onDone={() => setUploadDrawerOpen(false)}
        />
      </Drawer>

      {/* Document Content Modal */}
      <Modal
        title={contentData ? `文档内容 - ${contentData.original_name}` : '文档内容'}
        open={contentModalOpen}
        onCancel={() => {
          setContentModalOpen(false);
          setContentData(null);
        }}
        width={800}
        footer={null}
        destroyOnClose
      >
        {contentData && (
          <div>
            <Space style={{ marginBottom: 12 }}>
              <Tag>{contentData.format.toUpperCase()}</Tag>
              {contentData.page_count ? <Tag>共 {contentData.page_count} 页</Tag> : null}
              {contentData.chunk_count ? <Tag>{contentData.chunk_count} 个分块</Tag> : null}
            </Space>
            {contentData.content_type === 'image' ? (
              <Empty description="图片文件（不支持文本预览）" />
            ) : contentData.text ? (
              <pre
                style={{
                  maxHeight: '60vh',
                  overflow: 'auto',
                  background: '#fafafa',
                  padding: 16,
                  borderRadius: 8,
                  fontSize: 14,
                  lineHeight: 1.8,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  border: '1px solid #f0f0f0',
                }}
              >
                {contentData.text}
              </pre>
            ) : (
              <Empty description="文档暂无解析内容" />
            )}
          </div>
        )}
      </Modal>

      {/* Document Detail Drawer */}
      <Drawer
        title="文档详情"
        open={detailDrawerOpen}
        onClose={() => {
          setDetailDrawerOpen(false);
          setSelectedDoc(null);
        }}
        width={480}
      >
        {selectedDoc && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="文件名">
              {selectedDoc.original_name}
            </Descriptions.Item>
            <Descriptions.Item label="格式">
              <Tag color={formatColorMap[selectedDoc.format] || 'default'}>
                {selectedDoc.format.toUpperCase()}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="文件大小">
              {formatFileSize(selectedDoc.size_bytes)}
            </Descriptions.Item>
            <Descriptions.Item label="页数">
              {selectedDoc.page_count || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="解析状态">
              <Tag color={parseStatusColorMap[selectedDoc.parse_status]}>
                {parseStatusLabelMap[selectedDoc.parse_status]}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="分块数">
              {selectedDoc.chunk_count}
            </Descriptions.Item>
            <Descriptions.Item label="元数据">
              {selectedDoc.metadata.title && (
                <div>标题：{selectedDoc.metadata.title}</div>
              )}
              {selectedDoc.metadata.authors && (
                <div>作者：{selectedDoc.metadata.authors}</div>
              )}
              {selectedDoc.metadata.date && (
                <div>日期：{selectedDoc.metadata.date}</div>
              )}
              {selectedDoc.metadata.source && (
                <div>来源：{selectedDoc.metadata.source}</div>
              )}
              {!selectedDoc.metadata.title &&
                !selectedDoc.metadata.authors &&
                '无'}
            </Descriptions.Item>
            <Descriptions.Item label="是否内部文档">
              {selectedDoc.is_internal ? '是' : '否'}
            </Descriptions.Item>
            {selectedDoc.parse_error && (
              <Descriptions.Item label="解析错误">
                <Text type="danger">{selectedDoc.parse_error}</Text>
              </Descriptions.Item>
            )}
            <Descriptions.Item label="上传时间">
              {formatDate(selectedDoc.created_at)}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
}