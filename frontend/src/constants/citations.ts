import type { CitationConfidence } from '../api/types';

export const confidenceColorMap: Record<CitationConfidence, string> = {
  direct: 'green',
  fuzzy: 'gold',
  uncertain: 'red',
};

export const confidenceLabelMap: Record<CitationConfidence, string> = {
  direct: '直接',
  fuzzy: '模糊',
  uncertain: '不确定',
};