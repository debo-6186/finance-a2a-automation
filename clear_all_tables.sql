-- Clear All Tables Migration Script
-- This script safely deletes all data from all tables in the finance_a2a database
-- It handles foreign key constraints using TRUNCATE CASCADE

-- Start transaction for safety
BEGIN;

-- Display current row counts before deletion
SELECT 'BEFORE DELETION:' as status;
SELECT
    'users' as table_name,
    COUNT(*) as row_count
FROM users
UNION ALL
SELECT
    'conversation_sessions',
    COUNT(*)
FROM conversation_sessions
UNION ALL
SELECT
    'conversation_messages',
    COUNT(*)
FROM conversation_messages
UNION ALL
SELECT
    'agent_states',
    COUNT(*)
FROM agent_states;

-- Truncate all tables with CASCADE to handle foreign keys
-- TRUNCATE is faster than DELETE and automatically handles foreign key constraints
TRUNCATE TABLE
    users,
    conversation_sessions,
    conversation_messages,
    agent_states
CASCADE;

-- Display row counts after deletion
SELECT 'AFTER DELETION:' as status;
SELECT
    'users' as table_name,
    COUNT(*) as row_count
FROM users
UNION ALL
SELECT
    'conversation_sessions',
    COUNT(*)
FROM conversation_sessions
UNION ALL
SELECT
    'conversation_messages',
    COUNT(*)
FROM conversation_messages
UNION ALL
SELECT
    'agent_states',
    COUNT(*)
FROM agent_states;

-- Commit the transaction
COMMIT;

-- Reset sequences if any (for auto-increment IDs)
-- Not needed for this schema as we use VARCHAR IDs, but good practice

-- Vacuum tables to reclaim space
VACUUM ANALYZE users;
VACUUM ANALYZE conversation_sessions;
VACUUM ANALYZE conversation_messages;
VACUUM ANALYZE agent_states;

SELECT 'All tables cleared successfully!' as result;
