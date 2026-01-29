-- Add message credits column to users table
ALTER TABLE users ADD COLUMN message_credits INTEGER DEFAULT 30 NOT NULL;
