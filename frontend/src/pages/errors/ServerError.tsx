import { Result, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

export default function ServerError() {
  const navigate = useNavigate();

  return (
    <Result
      status="500"
      title="500"
      subTitle="抱歉，服务器发生了内部错误"
      extra={
        <Button type="primary" onClick={() => navigate('/projects')}>
          返回项目列表
        </Button>
      }
    />
  );
}