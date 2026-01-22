ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS market_preference VARCHAR(10);

COMMENT ON COLUMN conversation_sessions.market_preference IS 'User market preference: US or INDIA';
