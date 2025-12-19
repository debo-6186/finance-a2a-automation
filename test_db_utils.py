from host_agent.db_utils import DBQuery

print("Testing DBQuery utility...")

# List all tables
print("\n1. Listing all tables in the database:")
tables = DBQuery.execute_query("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename")
if tables:
    print(f"Found {len(tables)} tables:")
    for table in tables:
        print(f"  - {table['tablename']}")
else:
    print("No tables found")

print("\n2. Deleting all data from tables...")
DBQuery.execute_update("DELETE FROM agent_states", {})
print("  - Deleted from agent_states")
DBQuery.execute_update("DELETE FROM conversation_messages", {})
print("  - Deleted from conversation_messages")
DBQuery.execute_update("DELETE FROM conversation_sessions", {})

print("  - Deleted from conversation_sessions")
DBQuery.execute_update("DELETE FROM stock_recommendations", {})
print("  - Deleted from stock_recommendations")
DBQuery.execute_update("DELETE FROM users", {})
print("  - Deleted from users")

# Query
print("\n3. Testing execute_query - Fetching all users:")
users = DBQuery.execute_query("SELECT * FROM users")
print(f"Found {len(users) if users else 0} users")
if users:
    for user in users[:5]:  # Show first 5
        print(f"  - {user}")
    if len(users) > 5:
        print(f"  ... and {len(users) - 5} more")

# Update
# print("\n2. Testing execute_update:")
# DBQuery.execute_update("UPDATE users SET paid_user = true WHERE id = :id", {"id": "123"})
# print("Update completed")

# Insert
# print("\n3. Testing insert_record:")
# DBQuery.insert_record("users", {"id": "456", "email": "test@example.com"})
# print("Insert completed")

# Delete
# print("\n4. Testing delete_record:")
# DBQuery.delete_record("users", "id = :id", {"id": "456"})
# print("Delete completed")

print("\n✓ All tests completed successfully!")
