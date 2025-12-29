# Environment Configuration Guide

This document explains how to configure the application for different environments (local development vs production).

## Overview

The application now supports two environments:
- **Local**: For development on your local machine with local database and file storage
- **Production**: For deployment on AWS with RDS database and S3 file storage

## Configuration Files

### 1. `.env` File (host_agent/.env)

The `.env` file contains all environment-specific settings. The key variable is:

```bash
ENVIRONMENT=local  # Set to 'local' or 'production'
```

### 2. Database Configuration

**Local Environment:**
```bash
DATABASE_URL_LOCAL=postgresql://debojyotichakraborty@localhost:5432/finance_a2a
```

**Production Environment:**
```bash
DATABASE_URL_PRODUCTION=postgresql://postgres:PASSWORD@your-rds-endpoint.amazonaws.com:5432/finance-a2a-postgres
```

### 3. File Storage Configuration

**Local Environment:**
- Files are stored in `local_storage/portfolios/` directory
- No AWS credentials required

**Production Environment:**
- Files are stored in AWS S3 bucket
- Requires AWS credentials configured (`aws configure`)
- Bucket name: `finance-a2a-portfolio-statements`

## Switching Between Environments

### Running Locally

1. Set environment to local in `.env`:
   ```bash
   ENVIRONMENT=local
   ```

2. Ensure local PostgreSQL is running:
   ```bash
   # macOS
   brew services start postgresql

   # Or check status
   brew services list
   ```

3. Create local database if it doesn't exist:
   ```bash
   createdb finance_a2a
   ```

4. Start the application:
   ```bash
   cd host_agent
   python -m __main__
   ```

5. Check logs to verify local configuration:
   ```
   Database configuration loaded for local environment
   Using local storage: ./local_storage/portfolios
   ```

### Running in Production

1. Set environment to production in `.env`:
   ```bash
   ENVIRONMENT=production
   ```

2. Ensure AWS credentials are configured:
   ```bash
   aws configure
   # Enter your AWS Access Key ID
   # Enter your AWS Secret Access Key
   # Enter default region (e.g., us-east-1)
   ```

3. Update production database URL with correct RDS endpoint:
   ```bash
   DATABASE_URL_PRODUCTION=postgresql://postgres:PASSWORD@your-actual-rds-endpoint.amazonaws.com:5432/finance-a2a-postgres
   ```

4. Start the application:
   ```bash
   cd host_agent
   python -m __main__
   ```

5. Check logs to verify production configuration:
   ```
   Database configuration loaded for production environment
   Using S3 bucket: finance-a2a-portfolio-statements
   ```

## What Changes Between Environments

| Feature | Local | Production |
|---------|-------|------------|
| Database | Local PostgreSQL | AWS RDS PostgreSQL |
| File Storage | Local filesystem (`local_storage/`) | AWS S3 |
| SSL for DB | Not required | Required |
| AWS Credentials | Not required | Required |

## Troubleshooting

### Local Environment Issues

1. **Database Connection Error**
   ```
   Error: could not connect to server
   ```
   - Solution: Start PostgreSQL service
     ```bash
     brew services start postgresql
     ```

2. **File Upload Error**
   ```
   Error: It seems there was an issue reading your uploaded portfolio statement
   ```
   - Solution: Check that `local_storage/portfolios/` directory exists
     ```bash
     mkdir -p local_storage/portfolios
     ```

3. **Wrong Environment Detected**
   - Solution: Check `.env` file has `ENVIRONMENT=local`

### Production Environment Issues

1. **S3 Upload Error**
   ```
   Error: Unable to locate credentials
   ```
   - Solution: Configure AWS credentials
     ```bash
     aws configure
     ```

2. **RDS Connection Error**
   ```
   Error: could not translate host name "your-rds-endpoint.amazonaws.com"
   ```
   - Solution: Update `DATABASE_URL_PRODUCTION` with actual RDS endpoint

## Directory Structure

```
finance-a2a-automation/
├── host_agent/
│   ├── .env                    # Environment variables
│   ├── config.py              # Configuration management
│   ├── database.py            # Database models
│   ├── host/
│   │   ├── agent.py          # Host agent logic
│   │   └── pdf_analyzer.py  # PDF processing
│   └── __main__.py
├── local_storage/             # Local file storage (git-ignored)
│   └── portfolios/           # Portfolio PDFs stored here in local mode
└── ENVIRONMENT_CONFIGURATION.md  # This file
```

## Best Practices

1. **Never commit** `.env` file with production credentials
2. **Always verify** the environment setting before deploying
3. **Use local environment** for development and testing
4. **Test locally first** before deploying to production
5. **Keep local_storage/ directory** in .gitignore
6. **Backup production database** regularly
7. **Monitor S3 costs** in production

## Environment Variables Reference

| Variable | Required | Local | Production |
|----------|----------|-------|------------|
| `ENVIRONMENT` | Yes | `local` | `production` |
| `DATABASE_URL_LOCAL` | Yes (local) | PostgreSQL URL | - |
| `DATABASE_URL_PRODUCTION` | Yes (prod) | - | RDS URL |
| `LOCAL_STORAGE_PATH` | Yes (local) | Path | - |
| `S3_BUCKET_NAME` | Yes (prod) | - | Bucket name |
| `GOOGLE_API_KEY` | Yes | API key | API key |
| `FIREBASE_PROJECT_ID` | Yes | Project ID | Project ID |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Yes | Path to JSON | Path to JSON |

## Migration Guide

### Migrating from Old Configuration

If you're migrating from the old configuration where `DATABASE_URL` was hardcoded:

1. **Backup your `.env` file**
2. **Update `.env` with new format** (see example in host_agent/.env)
3. **Set `ENVIRONMENT=local` for local development**
4. **Test the application** to ensure it works
5. **For production**: Set `ENVIRONMENT=production` and deploy

### Example Migration

**Old `.env`:**
```bash
DATABASE_URL=postgresql://user@localhost:5432/db
```

**New `.env`:**
```bash
ENVIRONMENT=local
DATABASE_URL_LOCAL=postgresql://user@localhost:5432/db
DATABASE_URL_PRODUCTION=postgresql://user:pass@rds-endpoint:5432/db
```
