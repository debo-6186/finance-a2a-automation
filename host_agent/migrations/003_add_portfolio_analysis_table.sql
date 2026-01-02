-- Migration: Add portfolio_analysis table
-- Created: 2026-01-02
-- Description: Creates the portfolio_analysis table to store portfolio analysis data with investment details

-- Create portfolio_analysis table
CREATE TABLE IF NOT EXISTS portfolio_analysis (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    portfolio_analysis TEXT NOT NULL,
    investment_amount VARCHAR,
    email_id VARCHAR,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),

    -- Foreign key constraints
    CONSTRAINT fk_portfolio_analysis_session
        FOREIGN KEY (session_id)
        REFERENCES conversation_sessions(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_portfolio_analysis_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_portfolio_analysis_session_id
    ON portfolio_analysis(session_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_analysis_user_id
    ON portfolio_analysis(user_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_analysis_created_at
    ON portfolio_analysis(created_at DESC);

-- Add comments to table and columns
COMMENT ON TABLE portfolio_analysis IS 'Stores portfolio analysis data submitted by users including investment amount and email';
COMMENT ON COLUMN portfolio_analysis.id IS 'Unique identifier for the portfolio analysis record';
COMMENT ON COLUMN portfolio_analysis.session_id IS 'Reference to the conversation session';
COMMENT ON COLUMN portfolio_analysis.user_id IS 'Reference to the user who submitted the analysis';
COMMENT ON COLUMN portfolio_analysis.portfolio_analysis IS 'The raw portfolio analysis text containing stock information and investment details';
COMMENT ON COLUMN portfolio_analysis.investment_amount IS 'Extracted investment amount from the analysis';
COMMENT ON COLUMN portfolio_analysis.email_id IS 'Extracted email address for sending results';
COMMENT ON COLUMN portfolio_analysis.created_at IS 'Timestamp when the analysis was submitted';
