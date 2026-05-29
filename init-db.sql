-- Auto-init script for Docker PostgreSQL container.
-- Mounted as /docker-entrypoint-initdb.d/init.sql by docker-compose.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    major VARCHAR(128) NOT NULL,
    cas_account VARCHAR(128),
    cas_password_encrypted BYTEA,
    llm_api_key_encrypted BYTEA,
    working_dir VARCHAR(512),
    preferences JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(128) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(128) NOT NULL REFERENCES chat_sessions(session_id),
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS materials (
    file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    file_name VARCHAR(256) NOT NULL,
    file_type VARCHAR(128) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    subject_type VARCHAR(32) NOT NULL DEFAULT 'other',
    file_hash VARCHAR(64),
    vectorized BOOLEAN NOT NULL DEFAULT FALSE,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS personal_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    title VARCHAR(256) NOT NULL,
    description TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    location VARCHAR(256),
    is_done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    session_id VARCHAR(128) NOT NULL,
    action_type VARCHAR(32) NOT NULL,
    target_path VARCHAR(1024) NOT NULL,
    description TEXT NOT NULL,
    hitl_required BOOLEAN NOT NULL DEFAULT FALSE,
    hitl_approved BOOLEAN,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO alembic_version (version_num) VALUES ('28298627bda6')
ON CONFLICT DO NOTHING;
