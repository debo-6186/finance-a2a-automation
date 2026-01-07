-- Migration: Add user_whitelist table
-- Created: 2026-01-06
-- Description: Creates the user_whitelist table to manage user access and report generation limits

-- Create user_whitelist table
CREATE TABLE IF NOT EXISTS user_whitelist (
    id VARCHAR PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    whitelisted BOOLEAN NOT NULL DEFAULT TRUE,
    max_reports INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),

    -- Create index for email lookups
    CONSTRAINT idx_user_whitelist_email UNIQUE (email)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_user_whitelist_whitelisted
    ON user_whitelist(whitelisted);

-- Add comments to table and columns
COMMENT ON TABLE user_whitelist IS 'Manages user access control and report generation limits';
COMMENT ON COLUMN user_whitelist.id IS 'Unique identifier for the whitelist entry';
COMMENT ON COLUMN user_whitelist.email IS 'User email address (must be unique)';
COMMENT ON COLUMN user_whitelist.whitelisted IS 'Whether the user is whitelisted (true = allowed access)';
COMMENT ON COLUMN user_whitelist.max_reports IS 'Maximum number of reports the user can generate (0 = unlimited for paid users)';
COMMENT ON COLUMN user_whitelist.created_at IS 'Timestamp when the whitelist entry was created';
COMMENT ON COLUMN user_whitelist.updated_at IS 'Timestamp when the whitelist entry was last updated';
