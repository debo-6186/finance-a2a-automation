# Webhook Integration for Stock Analysis

## Overview
The stock analyser agent now includes a secure webhook integration function that can send analysis results to external systems, specifically the Activepieces webhook endpoint.

## Function: `send_analysis_to_webhook`

### Purpose
Securely sends stock analysis response data to the Activepieces webhook endpoint with proper authentication and error handling.

### Function Signature
```python
def send_analysis_to_webhook(
    analysis_response: str, 
    webhook_url: str = None, 
    username: str = None, 
    password: str = None
) -> str
```

### Parameters
- **`analysis_response`** (required): The analysis data to send
- **`webhook_url`** (optional): Custom webhook URL (defaults to Activepieces endpoint)
- **`username`** (optional): Basic auth username (defaults to environment variable)
- **`password`** (optional): Basic auth password (defaults to environment variable)

### Returns
- **Success**: Confirmation message with response details
- **Error**: Detailed error message explaining what went wrong

## Security Features

### 1. **Environment Variable Protection**
- Credentials are stored in environment variables, not hardcoded
- Function falls back to environment variables if parameters aren't provided
- No sensitive data in logs or error messages

### 2. **Secure Authentication**
- Basic authentication with base64 encoding
- Credentials are never logged or exposed
- SSL certificate verification enabled

### 3. **Input Validation**
- Checks for empty analysis responses
- Validates required authentication parameters
- Sanitizes input data before sending

### 4. **Request Security**
- 30-second timeout to prevent hanging requests
- Proper User-Agent header for identification
- Content-Type validation
- SSL verification enabled

## Configuration

### Environment Variables
Create a `.env` file in the `stockanalyser_agent` directory:

```bash
# Activepieces Webhook Configuration
ACTIVEPIECES_USERNAME=your_username_here
ACTIVEPIECES_PASSWORD=your_password_here

# Optional: Custom webhook URL
ACTIVEPIECES_WEBHOOK_URL=https://cloud.activepieces.com/api/v1/webhooks/BzkDtbfmZODV2C3jotH94
```

### Default Webhook Endpoint
```
https://cloud.activepieces.com/api/v1/webhooks/BzkDtbfmZODV2C3jotH94
```

## Usage Examples

### 1. **Basic Usage (Recommended)**
```python
# Uses environment variables for authentication
result = send_analysis_to_webhook("AAPL analysis: Strong buy recommendation")
```

### 2. **Custom Credentials**
```python
# Override with custom credentials
result = send_analysis_to_webhook(
    analysis_response="MSFT analysis: Hold recommendation",
    username="custom_user",
    password="custom_pass"
)
```

### 3. **Custom Webhook URL**
```python
# Use different webhook endpoint
result = send_analysis_to_webhook(
    analysis_response="GOOGL analysis: Sell recommendation",
    webhook_url="https://custom-endpoint.com/webhook"
)
```

## Error Handling

### HTTP Status Codes
- **200**: Success - Data sent successfully
- **401**: Authentication failed - Check credentials
- **404**: Endpoint not found - Verify URL
- **5xx**: Server error - Try again later

### Exception Handling
- **Timeout**: Request took too long to respond
- **Connection Error**: Unable to reach endpoint
- **SSL Error**: Certificate verification failed
- **General Errors**: Comprehensive error messages

## Integration with Agent

### Tool Registration
The webhook function is automatically registered as a tool:
```python
send_analysis_to_webhook_tool = FunctionTool(send_analysis_to_webhook)
```

### Agent Workflow
The agent can now:
1. Perform stock analysis
2. Send results to webhook automatically
3. Handle webhook responses and errors
4. Log all webhook activities

## Testing

### Test Script
Run the test script to verify functionality:
```bash
cd stockanalyser_agent
python test_webhook.py
```

### Test Coverage
- Environment variable validation
- Function import verification
- Webhook endpoint connectivity
- Authentication testing
- Error handling verification

## Dependencies

### Required Packages
- `requests`: HTTP client library
- `python-dotenv`: Environment variable management
- `base64`: Credential encoding (built-in)

### Installation
```bash
# Install dependencies
uv sync

# Or manually install
pip install requests python-dotenv
```

## Best Practices

### 1. **Credential Management**
- Never hardcode credentials in code
- Use environment variables or secure secret management
- Rotate credentials regularly

### 2. **Error Handling**
- Always check return values from the function
- Implement retry logic for transient failures
- Log errors for debugging

### 3. **Data Validation**
- Validate analysis data before sending
- Check data size and format
- Sanitize sensitive information

### 4. **Monitoring**
- Monitor webhook success rates
- Track response times
- Alert on authentication failures

## Troubleshooting

### Common Issues

#### 1. **Authentication Failed**
- Verify `ACTIVEPIECES_USERNAME` and `ACTIVEPIECES_PASSWORD` are set
- Check credentials are correct
- Ensure environment variables are loaded

#### 2. **Connection Timeout**
- Check network connectivity
- Verify webhook endpoint is accessible
- Consider increasing timeout if needed

#### 3. **SSL Certificate Issues**
- Verify endpoint uses valid SSL certificate
- Check system time is correct
- Disable SSL verification only if necessary (not recommended)

#### 4. **Empty Response Data**
- Validate analysis_response parameter
- Check for empty strings or None values
- Ensure data is properly formatted

### Debug Mode
Enable detailed logging by setting log level to DEBUG in your logger configuration.

## Future Enhancements

### Potential Improvements
1. **Retry Logic**: Automatic retry for failed requests
2. **Rate Limiting**: Prevent overwhelming webhook endpoints
3. **Batch Processing**: Send multiple analyses in single request
4. **Response Validation**: Verify webhook response format
5. **Metrics Collection**: Track webhook performance metrics

### Integration Possibilities
- **Slack/Discord**: Send analysis notifications
- **Email**: Email analysis reports
- **Database**: Store analysis results
- **Analytics**: Track analysis patterns

## Support

For issues with the webhook integration:
1. Check environment variables are set correctly
2. Verify webhook endpoint is accessible
3. Review logs for detailed error messages
4. Test with the provided test script
5. Check network connectivity and firewall settings
