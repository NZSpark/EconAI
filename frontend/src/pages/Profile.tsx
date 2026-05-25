import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Typography, Descriptions, Divider, Form, Input, Button, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useAuth } from '../hooks/useAuth';

const { Title } = Typography;

interface Props {
  /** If true, user is forced to change password before accessing the app */
  force?: boolean;
}

export default function Profile({ force = false }: Props) {
  const navigate = useNavigate();
  const { user, hasForcePasswordChange, changePassword, logout } = useAuth();
  const [form] = Form.useForm();

  // If not forced and force_password_change was already cleared, redirect
  useEffect(() => {
    if (force && !hasForcePasswordChange) {
      navigate('/projects', { replace: true });
    }
  }, [force, hasForcePasswordChange, navigate]);

  const handleChangePassword = async (values: {
    old_password: string;
    new_password: string;
    confirm_password: string;
  }) => {
    if (values.new_password !== values.confirm_password) {
      message.error('两次输入的新密码不一致');
      return;
    }
    try {
      await changePassword(values.old_password, values.new_password);
      message.success('密码修改成功');
      form.resetFields();
      if (force) {
        // After forced password change, redirect to main app
        navigate('/projects', { replace: true });
      }
    } catch (err: any) {
      const errorCodeMap: Record<string, string> = {
        AUTH_INVALID_PASSWORD: '当前密码错误',
        AUTH_PASSWORD_SAME: '新密码不能与当前密码相同',
        AUTH_LDAP_PASSWORD: 'LDAP用户请通过企业账号管理修改密码',
      };
      if (err?.code && errorCodeMap[err.code]) {
        message.error(errorCodeMap[err.code]);
      } else if (err?.message) {
        message.error(err.message);
      } else {
        message.error('密码修改失败');
      }
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      {force && (
        <div
          style={{
            background: '#fff7e6',
            border: '1px solid #ffd591',
            borderRadius: 8,
            padding: '16px 24px',
            marginBottom: 24,
          }}
        >
          <Typography.Text strong style={{ color: '#d46b08' }}>
            ⚠ 管理员已重置您的密码，请设置新密码后继续使用系统。
          </Typography.Text>
        </div>
      )}

      <Card>
        <Title level={4} style={{ marginBottom: 24 }}>
          个人设置
        </Title>

        <Descriptions column={1} bordered size="small" style={{ marginBottom: 24 }}>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="显示名">{user?.display_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="角色">
            {user?.role === 'system_admin'
              ? '系统管理员'
              : user?.role === 'project_admin'
                ? '项目管理员'
                : user?.role === 'senior_researcher'
                  ? '高级研究员'
                  : '分析员'}
          </Descriptions.Item>
          <Descriptions.Item label="认证方式">
            {user?.role === 'system_admin' ? '本地' : '本地'}
          </Descriptions.Item>
        </Descriptions>

        <Divider orientation={"left" as any} plain>
          修改密码
        </Divider>

        <Form
          form={form}
          layout="vertical"
          onFinish={handleChangePassword}
          style={{ maxWidth: 360 }}
        >
          <Form.Item
            name="old_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="输入当前密码"
            />
          </Form.Item>

          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 8, message: '密码至少8位' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="输入新密码（至少8位）"
            />
          </Form.Item>

          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请确认新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="再次输入新密码"
            />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              {force ? '设置新密码并继续' : '修改密码'}
            </Button>
          </Form.Item>
        </Form>

        {force && (
          <Typography.Text
            type="secondary"
            style={{ display: 'block', textAlign: 'center', fontSize: 13 }}
          >
            如需退出，请
            <Button
              type="link"
              size="small"
              onClick={async () => {
                await logout();
                navigate('/login', { replace: true });
              }}
            >
              退出登录
            </Button>
          </Typography.Text>
        )}
      </Card>
    </div>
  );
}
