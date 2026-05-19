import { Steps, Typography } from 'antd';
import type { TaskProgress as TaskProgressType } from '../api/types';

const { Text } = Typography;

interface TaskProgressProps {
  progress: TaskProgressType | null;
  status: string;
}

export default function TaskProgress({ progress, status }: TaskProgressProps) {
  if (!progress) {
    if (status === 'pending') {
      return <Text type="secondary">等待开始...</Text>;
    }
    if (status === 'completed') {
      return <Text type="success">任务已完成</Text>;
    }
    if (status === 'failed') {
      return <Text type="danger">任务执行失败</Text>;
    }
    if (status === 'cancelled') {
      return <Text type="secondary">任务已取消</Text>;
    }
    return null;
  }

  const { step_index, total_steps_estimate, message } = progress;

  // Build fake steps up to the total estimate
  const steps = [];
  const stepNames = [
    '计划',
    '检索',
    '生成',
    '校验',
    '格式化',
    '导出',
  ];

  for (let i = 0; i < Math.min(total_steps_estimate, stepNames.length); i++) {
    steps.push({ title: stepNames[i] });
  }

  // If more steps than names, add numbered ones
  for (let i = stepNames.length; i < total_steps_estimate; i++) {
    steps.push({ title: `步骤 ${i + 1}` });
  }

  let currentStep = 0;
  if (status === 'completed') {
    currentStep = total_steps_estimate;
  } else if (status === 'failed') {
    currentStep = step_index;
  } else {
    currentStep = step_index;
  }

  return (
    <div>
      <Steps
        current={currentStep}
        size="small"
        status={status === 'failed' ? 'error' : status === 'completed' ? 'finish' : 'process'}
        items={steps}
      />
      {message && (
        <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
          {message}
        </Text>
      )}
      {status === 'running' && (
        <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
          步骤 {step_index + 1}/{total_steps_estimate}，预计剩余时间：约
          {(total_steps_estimate - step_index) * 2} 分钟
        </Text>
      )}
    </div>
  );
}