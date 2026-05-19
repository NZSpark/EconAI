import { Result, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

export default function Forbidden() {
  const navigate = useNavigate();

  return (
    <Result
      status="403"
      title="403"
      subTitle="抱歉，您没有访问该页面的权限"
      extra={
        <Button type="primary" onClick={() => navigate('/projects')}>
          返回项目列表
        </Button>
      }
    />
  );
}