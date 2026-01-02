# Database Migrations

This directory contains database migration scripts for the Host Agent.

## Migration Files

- `000_add_portfolio_statement_uploaded_field.sql` - Adds portfolio statement uploaded flag to sessions
- `001_add_stock_recommendations_table.sql` - Adds the `stock_recommendations` table to store stock analysis recommendations
- `002_add_input_format_column.sql` - Adds input format column to track how portfolio data was submitted
- `003_add_portfolio_analysis_table.sql` - Adds the `portfolio_analysis` table to store portfolio analysis data with investment details

## Running Migrations

### Option 1: Run all migrations using Python script

```bash
cd /Users/debojyotichakraborty/codebase/finance-a2a-automation/host_agent
python migrations/run_migrations.py
```

### Option 2: Run a specific migration manually

```bash
cd /Users/debojyotichakraborty/codebase/finance-a2a-automation/host_agent
psql $DATABASE_URL -f migrations/001_add_stock_recommendations_table.sql
```

### Option 3: Run from Python code

```python
from database import init_db

# This will create all tables including the new stock_recommendations table
init_db()
```

## Migration Naming Convention

Migration files should follow the pattern:
```
<number>_<description>.sql
```

For example:
- `001_add_stock_recommendations_table.sql`
- `002_add_user_preferences.sql`

## Database Schema

### Stock Recommendations Table

After running migrations, the `stock_recommendations` table will have the following structure:

| Column         | Type      | Description                                                    |
|----------------|-----------|----------------------------------------------------------------|
| id             | VARCHAR   | Primary key - unique identifier for the recommendation         |
| session_id     | VARCHAR   | Foreign key to conversation_sessions table                     |
| user_id        | VARCHAR   | Foreign key to users table                                     |
| recommendation | JSONB     | JSON object containing the complete recommendation data        |
| created_at     | TIMESTAMP | Timestamp when the recommendation was created                  |

#### Indexes

- `idx_stock_recommendations_session_id` - Index on session_id for faster lookups
- `idx_stock_recommendations_user_id` - Index on user_id for faster user queries
- `idx_stock_recommendations_created_at` - Index on created_at for sorting

### Portfolio Analysis Table

The `portfolio_analysis` table stores portfolio analysis data:

| Column              | Type      | Description                                                    |
|---------------------|-----------|----------------------------------------------------------------|
| id                  | VARCHAR   | Primary key - unique identifier for the analysis               |
| session_id          | VARCHAR   | Foreign key to conversation_sessions table                     |
| user_id             | VARCHAR   | Foreign key to users table                                     |
| portfolio_analysis  | TEXT      | Raw portfolio analysis text with stock information             |
| investment_amount   | VARCHAR   | Extracted investment amount from the analysis                  |
| email_id            | VARCHAR   | Extracted email address for sending results                    |
| created_at          | TIMESTAMP | Timestamp when the analysis was submitted                      |

#### Indexes

- `idx_portfolio_analysis_session_id` - Index on session_id for faster lookups
- `idx_portfolio_analysis_user_id` - Index on user_id for faster user queries
- `idx_portfolio_analysis_created_at` - Index on created_at for sorting

## Recommendation JSON Structure

The `recommendation` column stores a JSON object with the following structure:

```json
{
  "allocation_breakdown": [
    {
      "ticker": "AAPL",
      "percentage": "25%",
      "investment_amount": "$2500"
    }
  ],
  "individual_stock_recommendations": [
    {
      "ticker": "AAPL",
      "recommendation": "BUY",
      "investment_amount": "$2500",
      "key_metrics": "Current P/E [28.5], Target Upside [15%], Analyst Rating [Buy], Revenue Growth [8%]",
      "reasoning": "Strong fundamentals with positive analyst sentiment..."
    }
  ],
  "risk_warnings": [
    "Market volatility may impact short-term returns",
    "Sector concentration in technology stocks"
  ]
}
```

## Troubleshooting

### Migration fails with "relation already exists"

If the table already exists, you can either:
1. Drop the table first: `DROP TABLE stock_recommendations CASCADE;`
2. Skip the migration (table is already created)

### Missing DATABASE_URL environment variable

Make sure `DATABASE_URL` is set in your `.env` file:
```
DATABASE_URL=postgresql://postgres:password@localhost:5432/finance_a2a
```
