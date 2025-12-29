# Host Agent Connection Error Fix

## Problem Summary

The host_agent was failing to connect to the stockanalyser_agent during startup in AWS ECS with the following error:

```
HTTP Error 503: Network communication error fetching agent card from http://localhost:10002/.well-known/agent-card.json: All connection attempts failed
```

## Root Causes

### 1. Environment Variable Name Mismatch
- **Terraform** was setting: `STOCK_ANALYSER_URL`
- **Config.py** was expecting: `STOCK_ANALYSER_AGENT_URL`
- Result: The config couldn't read the URL from terraform, falling back to default `http://localhost:10002`

### 2. Hardcoded URL in Application Code
- **host_agent/__main__.py** had hardcoded agent URLs:
  ```python
  AGENT_URLS = [
      "http://localhost:10002",  # Hardcoded - doesn't work in ECS!
  ]
  ```
- This should have been reading from the config instead

## Solution Applied

### 1. Fixed Terraform Configuration
**File**: `terraform/main.tf:674`

Changed:
```hcl
{
  name  = "STOCK_ANALYSER_URL"  # Wrong variable name
  value = "http://stockanalyser-agent.local:10002"
}
```

To:
```hcl
{
  name  = "STOCK_ANALYSER_AGENT_URL"  # Correct variable name matching config.py
  value = "http://stockanalyser-agent.local:10002"
}
```

### 2. Fixed Docker Compose Configuration
**File**: `docker-compose.aws.yml:84-85`

Changed:
```yaml
- STOCK_ANALYSER_URL=http://stockanalyser_agent:10002
- STOCK_REPORT_ANALYSER_URL=http://stockreport_analyser_agent:10003
```

To:
```yaml
- STOCK_ANALYSER_AGENT_URL=http://stockanalyser_agent:10002
- STOCK_REPORT_ANALYSER_AGENT_URL=http://stockreport_analyser_agent:10003
```

### 3. Fixed Host Agent Code
**File**: `host_agent/__main__.py:117-123`

Changed:
```python
# Global variable to store the host agent instance
host_agent_instance: Optional[HostAgent] = None

# Agent URLs configuration
AGENT_URLS = [
    "http://localhost:10002",  # Stock Analyser Agent
    # Stock Report Analyser Agent removed - now integrated locally as a sub-agent
]
```

To:
```python
# Global variable to store the host agent instance
host_agent_instance: Optional[HostAgent] = None

# Import configuration
from config import current_config as Config

# Agent URLs configuration - read from environment via config
AGENT_URLS = [
    Config.STOCK_ANALYSER_AGENT_URL,  # Stock Analyser Agent
    # Stock Report Analyser Agent removed - now integrated locally as a sub-agent
]
```

## Deployment Steps

To deploy these fixes to AWS ECS:

### 1. Rebuild and Push Host Agent Docker Image

```bash
# Navigate to project root
cd /Users/debojyotichakraborty/codebase/finance-a2a-automation

# Build the host_agent image
docker build -t finance-a2a/host-agent:latest ./host_agent

# Tag for ECR
docker tag finance-a2a/host-agent:latest 156041436571.dkr.ecr.us-east-1.amazonaws.com/finance-a2a/host-agent:latest

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 156041436571.dkr.ecr.us-east-1.amazonaws.com

# Push to ECR
docker push 156041436571.dkr.ecr.us-east-1.amazonaws.com/finance-a2a/host-agent:latest
```

### 2. Update Terraform Configuration

```bash
# Navigate to terraform directory
cd terraform

# Plan the changes (verify environment variable update)
terraform plan

# Apply the changes
terraform apply
```

### 3. Force New Deployment (ECS will pull new image)

```bash
# Force new deployment of host-agent service
aws ecs update-service \
  --cluster finance-a2a-cluster \
  --service host-agent \
  --force-new-deployment \
  --region us-east-1

# Monitor deployment
aws ecs describe-services \
  --cluster finance-a2a-cluster \
  --services host-agent \
  --region us-east-1 \
  --query 'services[0].deployments'
```

### 4. Verify the Fix

```bash
# Check host agent logs - should see successful agent connection
aws logs tail /ecs/finance-a2a-host-agent --follow --region us-east-1

# Look for:
# ✅ "agent_info: [...]" with connected agents (not empty)
# ✅ No "❌ No agents connected successfully!" error
# ✅ No "HTTP Error 503" messages
```

## Expected Behavior After Fix

After deployment, the host_agent logs should show:

```
INFO host_agent_api.host_agent: Attempting to connect to agent at http://stockanalyser-agent.local:10002
INFO host_agent_api.host_agent: Successfully connected to agent: stock_analyser
INFO host_agent_api.host_agent: agent_info: [{'name': 'stock_analyser', 'url': 'http://stockanalyser-agent.local:10002', ...}]
INFO host_agent_api: Host Agent initialized successfully
```

Instead of:
```
ERROR host_agent_api.host_agent: Unexpected error connecting to http://localhost:10002: HTTP Error 503
ERROR host_agent_api.host_agent: ❌ No agents connected successfully!
```

## Verification Status

- ✅ Stockanalyser agent is running and healthy (verified via logs)
- ✅ Terraform configuration fixed
- ✅ Docker Compose configuration fixed
- ✅ Host agent code fixed to read from config
- ⏳ Awaiting deployment to AWS ECS

## Notes

- The stockanalyser agent is accessible at `http://stockanalyser-agent.local:10002` via AWS Cloud Map service discovery
- The `.local` domain is created by the private DNS namespace in terraform (line 436)
- Health checks confirm the stockanalyser agent is responding correctly
