import { Popover, Descriptions, Tag, Typography } from 'antd';
import type { Citation } from '../api/types';
import { confidenceColorMap, confidenceLabelMap } from './CitationBadge';

const { Text, Paragraph } = Typography;

interface CitationPopoverProps {
  citation: Citation;
  children: React.ReactNode;
}

export default function CitationPopover({
  citation,
  children,
}: CitationPopoverProps) {
  const { confidence, source } = citation;
  const confidenceColor = confidenceColorMap[confidence];
  const confidenceLabel = confidenceLabelMap[confidence];

  const content = (
    <div style={{ maxWidth: 360 }}>
      <Descriptions column={1} size="small" bordered={false}>
        <Descriptions.Item label="置信度">
          <Tag color={confidenceColor}>{confidenceLabel}</Tag>
        </Descriptions.Item>
        {source && (
          <>
            <Descriptions.Item label="来源文档">
              <Text strong>{source.document_title}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="页码范围">
              第 {source.page_start}-{source.page_end} 页
            </Descriptions.Item>
            <Descriptions.Item label="原文摘录">
              <Paragraph
                ellipsis={{ rows: 4, expandable: true }}
                style={{ marginBottom: 0, fontSize: '0.85em', color: '#666' }}
              >
                {source.excerpt}
              </Paragraph>
            </Descriptions.Item>
          </>
        )}
        {!source && (
          <Descriptions.Item label="说明">
            <Text type="secondary">该引用来源暂未匹配到原文</Text>
          </Descriptions.Item>
        )}
        <Descriptions.Item label="引用原文">
          <Text style={{ fontSize: '0.85em' }}>{citation.sentence}</Text>
        </Descriptions.Item>
      </Descriptions>
    </div>
  );

  return (
    <Popover content={content} title="引用详情" trigger="click">
      {children}
    </Popover>
  );
}