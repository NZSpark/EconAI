-- =============================================================================
-- EconAI Seed Data
-- Default admin user + example project group
-- =============================================================================

-- Password: Admin@123456 (bcrypt hash)
-- Generated with: python -c "import bcrypt; print(bcrypt.hashpw(b'Admin@123456', bcrypt.gensalt()).decode())"
INSERT INTO users (id, username, email, display_name, hashed_password, role, auth_provider, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'admin',
    'admin@econai.local',
    'System Administrator',
    '$2b$12$LJ3m4ys3GZfnYMz8kVsKaOmvGq4vGd9mN5ZqwVN1rQjqJqIhRqHqK',
    'system_admin',
    'local',
    TRUE
) ON CONFLICT (username) DO NOTHING;

-- Example project group
INSERT INTO project_groups (id, name, description)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    'Default Group',
    'Default project group for initial setup'
) ON CONFLICT DO NOTHING;

-- Add admin to default group
INSERT INTO project_group_members (group_id, user_id, role)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000001',
    'system_admin'
) ON CONFLICT (group_id, user_id) DO NOTHING;