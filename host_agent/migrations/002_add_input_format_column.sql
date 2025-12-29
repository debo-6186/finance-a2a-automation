ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS input_format VARCHAR(20);

COMMENT ON COLUMN conversation_sessions.input_format IS 'Format of portfolio input: pdf, image, or text';
