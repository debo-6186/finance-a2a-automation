-- Migration script to add CASCADE UPDATE to foreign key constraints
-- This allows user ID updates to cascade to related tables

-- First, drop the existing foreign key constraints
ALTER TABLE conversation_sessions DROP CONSTRAINT IF EXISTS conversation_sessions_user_id_fkey;
ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_user_id_fkey;
ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_session_id_fkey;
ALTER TABLE agent_states DROP CONSTRAINT IF EXISTS agent_states_session_id_fkey;
ALTER TABLE stock_recommendations DROP CONSTRAINT IF EXISTS stock_recommendations_session_id_fkey;
ALTER TABLE stock_recommendations DROP CONSTRAINT IF EXISTS stock_recommendations_user_id_fkey;

-- Re-create foreign key constraints with CASCADE UPDATE
ALTER TABLE conversation_sessions
    ADD CONSTRAINT conversation_sessions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE conversation_messages
    ADD CONSTRAINT conversation_messages_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE conversation_messages
    ADD CONSTRAINT conversation_messages_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE agent_states
    ADD CONSTRAINT agent_states_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE stock_recommendations
    ADD CONSTRAINT stock_recommendations_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE stock_recommendations
    ADD CONSTRAINT stock_recommendations_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE ON DELETE CASCADE;
