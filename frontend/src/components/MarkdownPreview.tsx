import ReactMarkdown from 'react-markdown';
import { Typography } from 'antd';

const { Text } = Typography;

interface MarkdownPreviewProps {
  content: string;
  citationMap?: Map<number, { refId: string; confidence: string; sourceTitle?: string }>;
  onCitationClick?: (index: number) => void;
}

export default function MarkdownPreview({
  content,
  citationMap,
  onCitationClick,
}: MarkdownPreviewProps) {
  return (
    <div className="markdown-preview" style={{ lineHeight: 1.8, fontSize: 15 }}>
      <ReactMarkdown
        components={{
          // Render citation markers as clickable superscript badges
          sup: ({ children, ...props }) => {
            const text = String(children);
            // Match citation reference patterns like [1], [2], [1,2,3]
            const match = text.match(/^\[(\d+(?:,\d+)*)\]$/);
            if (match && citationMap) {
              const indices = match[1].split(',').map(Number);
              return (
                <>
                  {indices.map((idx) => {
                    const citation = citationMap.get(idx);
                    return (
                      <Text
                        key={idx}
                        onClick={() => onCitationClick?.(idx)}
                        style={{
                          color: citation && citation.confidence === 'direct'
                            ? '#52c41a'
                            : citation && citation.confidence === 'fuzzy'
                            ? '#faad14'
                            : citation && citation.confidence === 'uncertain'
                            ? '#ff4d4f'
                            : '#1677ff',
                          cursor: 'pointer',
                          verticalAlign: 'super',
                          fontSize: '0.8em',
                          margin: '0 2px',
                          userSelect: 'none',
                        }}
                        title={
                          citation
                            ? `[${idx}] ${citation.sourceTitle || citation.refId} (${citation.confidence})`
                            : `[${idx}]`
                        }
                      >
                        [{idx}]
                      </Text>
                    );
                  })}
                </>
              );
            }
            return <sup {...props}>{children}</sup>;
          },
          // Style headings
          h1: ({ children, ...props }) => (
            <h1 style={{ fontSize: '1.6em', marginTop: '1.5em', marginBottom: '0.5em' }} {...props}>
              {children}
            </h1>
          ),
          h2: ({ children, ...props }) => (
            <h2 style={{ fontSize: '1.4em', marginTop: '1.2em', marginBottom: '0.5em' }} {...props}>
              {children}
            </h2>
          ),
          h3: ({ children, ...props }) => (
            <h3 style={{ fontSize: '1.2em', marginTop: '1em', marginBottom: '0.4em' }} {...props}>
              {children}
            </h3>
          ),
          // Style tables
          table: ({ children, ...props }) => (
            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  borderCollapse: 'collapse',
                  width: '100%',
                  marginBottom: 16,
                }}
                {...props}
              >
                {children}
              </table>
            </div>
          ),
          th: ({ children, ...props }) => (
            <th
              style={{
                border: '1px solid #e8e8e8',
                padding: '8px 12px',
                backgroundColor: '#fafafa',
                textAlign: 'left',
              }}
              {...props}
            >
              {children}
            </th>
          ),
          td: ({ children, ...props }) => (
            <td
              style={{
                border: '1px solid #e8e8e8',
                padding: '8px 12px',
              }}
              {...props}
            >
              {children}
            </td>
          ),
          // Paragraph styling
          p: ({ children, ...props }) => (
            <p style={{ margin: '0.5em 0' }} {...props}>
              {children}
            </p>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}