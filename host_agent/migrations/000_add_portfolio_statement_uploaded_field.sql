-- Migration script to add portfolio_statement_uploaded field to existing conversation_sessions table

-- Add the portfolio_statement_uploaded column if it doesn't exist
ALTER TABLE conversation_sessions 
ADD COLUMN IF NOT EXISTS portfolio_statement_uploaded BOOLEAN NOT NULL DEFAULT FALSE;

-- Optionally, you can add a comment
COMMENT ON COLUMN conversation_sessions.portfolio_statement_uploaded IS 'Tracks whether a portfolio statement has been uploaded and processed in this session';