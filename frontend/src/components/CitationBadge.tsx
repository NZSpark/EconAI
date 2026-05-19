import { Tag } from 'antd';
import type { CitationConfidence } from '../api/types';

const confidenceColorMap: Record<CitationConfidence, string> = {
  direct: 'green',
  fuzzy: 'gold',
  uncertain: 'red',
};

const confidenceLabelMap: Record<CitationConfidence, string> = {
  direct: '直接',
  fuzzy: '模糊',
  uncertain: '不确定',
};

interface CitationBadgeProps {
  index: number;
  confidence?: CitationConfidence;
  onClick?: () => void;
}

export { confidenceColorMap, confidenceLabelMap };

export default function CitationBadge({
  index,
  confidence,
  onClick,
}: CitationBadgeProps) {
  const color = confidence ? confidenceColorMap[confidence] : undefined;

  return (
    <Tag
      color={color}
      onClick={onClick}
      style={{
        cursor: onClick ? 'pointer' : 'default',
        fontSize: '0.75em',
        verticalAlign: 'super',
        lineHeight: 1,
        padding: '0 4px',
        marginLeft: 2,
        marginRight: 2,
      }}
    >
      [{index}]
    </Tag>
  );
}