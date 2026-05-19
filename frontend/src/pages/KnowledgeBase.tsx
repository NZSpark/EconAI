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
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRequest } from '../hooks/useRequest';
import { listDocuments, uploadDocument, deleteDocument, reindexDocument, getDocument } from '../api/documents';
import { searchProjectKB } from '../api/search';
import DocumentUpload from '../components/DocumentUpload';
import type { DocumentItem, SearchResultChunk } from '../api/types';

const { Title, Text } = Typography;

const parseStatusColorMap: Record<string, string> = {
  pending: 'default',
  parsing: 'processing',
  ready: 'green',
  error: 'red',
  deleted: 'default',
};

const parseStatusLabelMap: Record<string, string> = {
  pending: '等待中',
  parsing: '解析中',
  ready: '就绪',
  error: '解析失败',
  deleted: '已删除',
};

const formatColorMap: Record<string, string> = {
  pdf: 'red',
  docx: 'blue',
  doc: 'blue',
  xlsx: 'green',
  xls: 'green',
  csv: 'green',
  pptx: 'orange',
  ppt: 'orange',
  md: 'purple',
  txt: 'default',
  html: 'cyan',
  eml: 'geekblue',
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

export default function KnowledgeBase() {
  const { id: projectId } = useParams<{ id: string }>();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [uploadDrawerOpen, setUploadDrawerOpen] = useState(false);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResultChunk[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchTime, setSearchTime] = useState(0);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const loadDocs = useCallback(async () => {
    if (!projectId) throw new Error('No project ID');
    return listDocuments(projectId, {
      page,
      page_size: pageSize,
      status: statusFilter,
    });
  }, [projectId, page, pageSize, statusFilter]);

  const { data, loading, error, run: refresh } = useRequest(loadDocs);

  const handleUpload = async (file: File, isInternal: boolean) => {
    if (!projectId) return;
    await uploadDocument(projectId, file, isInternal);
    refresh();
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
    try {
      await reindexDocument(projectId, docId);
      message.success('已触发重新索引');
      refresh();
    } catch {
      message.error('重新索引失败');
    }
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

  const handleSearch = async () => {
    if (!projectId || !searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await searchProjectKB(projectId, {
        query: searchQuery,
        top_k: 10,
      });
      setSearchResults(res.results);
      setSearchTotal(res.total_hits);
      setSearchTime(res.search_time_ms);
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
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, record: DocumentItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record)}
          >
            详情
          </Button>
          {record.parse_status === 'ready' && (
            <Button
              type="link"
              size="small"
              icon={<RedoOutlined />}
              onClick={() => handleReindex(record.document_id)}
            >
              重索引
            </Button>
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
            onSearch={handleSearch}
            onPressEnter={handleSearch}
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
                      <Text>{item.content}</Text>
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
          projectId={projectId || ''}
          onUpload={async (file) => {
            await handleUpload(file, false);
            setUploadDrawerOpen(false);
          }}
        />
      </Drawer>

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
              {new Date(selectedDoc.created_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
}