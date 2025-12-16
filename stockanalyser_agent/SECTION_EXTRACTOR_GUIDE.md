# Section Extractor Usage Guide

This guide shows how to extract specific sections from portfolio analysis responses using keyword-based filtering instead of delimiters.

## Quick Start

```python
from section_extractor import SectionExtractor

# Your analysis response text
analysis_response = """1. PORTFOLIO ASSESSMENT
The existing portfolio is heavily concentrated...
..."""

extractor = SectionExtractor()

# Extract ALLOCATION BREAKDOWN
allocation = extractor.extract_allocation_breakdown(analysis_response)
print(allocation)

# Extract RISK WARNINGS
warnings = extractor.extract_risk_warnings(analysis_response)
for warning in warnings:
    print(f"- {warning}")

# Extract BUY recommendations only
buy_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='BUY')
for rec in buy_recs:
    print(f"{rec['ticker']}: ${rec['investment_amount']}")
```

## Available Methods

### 1. Extract Allocation Breakdown

```python
# Without justification
allocation = extractor.extract_allocation_breakdown(
    analysis_response,
    include_justification=False
)
# Returns:
# ALLOCATION BREAKDOWN - October 07, 2025
# - NVDA: 25% ($400)
# - MSFT: 25% ($400)
# - META: 25% ($400)
# - AVGO: 25% ($400)
# Total: 100% ($1600)

# With justification
allocation_full = extractor.extract_allocation_breakdown(
    analysis_response,
    include_justification=True
)
# Returns same as above plus:
# Justification: This equal-weight allocation...
```

### 2. Extract Risk Warnings

```python
warnings = extractor.extract_risk_warnings(analysis_response)
# Returns list of strings:
# [
#   "High-Beta Stocks: NVDA (beta 2.12)...",
#   "Valuation Risk: TSLA and SPOT...",
#   "Sector Concentration: The recommended portfolio..."
# ]

# Use the warnings
for i, warning in enumerate(warnings, 1):
    print(f"{i}. {warning}")
```

### 3. Extract Stock Recommendations

```python
# Get all BUY recommendations
buy_recs = extractor.extract_stock_recommendations(
    analysis_response,
    recommendation_type='BUY'
)

# Get all HOLD recommendations
hold_recs = extractor.extract_stock_recommendations(
    analysis_response,
    recommendation_type='HOLD'
)

# Get all SELL recommendations
sell_recs = extractor.extract_stock_recommendations(
    analysis_response,
    recommendation_type='SELL'
)

# Get ALL recommendations (no filter)
all_recs = extractor.extract_stock_recommendations(analysis_response)

# Each recommendation is a dictionary:
# {
#     'ticker': 'NVDA',
#     'recommendation': 'BUY',
#     'investment_amount': '$400',
#     'key_metrics': 'Current P/E [52.8], Target Upside [16.0%]...',
#     'reasoning': 'NVDA meets all buy criteria...'
# }
```

### 4. Extract Specific Section

```python
# Extract PORTFOLIO ASSESSMENT
portfolio_assessment = extractor.extract_section(
    analysis_response,
    'portfolio_assessment'
)

# Extract ALLOCATION BREAKDOWN (raw)
allocation = extractor.extract_section(
    analysis_response,
    'allocation_breakdown'
)

# Extract INDIVIDUAL STOCK RECOMMENDATIONS (raw)
recommendations = extractor.extract_section(
    analysis_response,
    'individual_recommendations'
)

# Extract RISK WARNINGS (raw)
risk_warnings = extractor.extract_section(
    analysis_response,
    'risk_warnings'
)
```

### 5. Extract All Sections at Once

```python
all_sections = extractor.extract_all_sections(analysis_response)

# Returns dictionary:
# {
#     'portfolio_assessment': 'PORTFOLIO ASSESSMENT\nThe existing...',
#     'allocation_breakdown': 'ALLOCATION BREAKDOWN - October 07...',
#     'individual_recommendations': 'INDIVIDUAL STOCK RECOMMENDATIONS...',
#     'risk_warnings': 'RISK WARNINGS\n- High-Beta Stocks...'
# }

# Access individual sections
portfolio = all_sections['portfolio_assessment']
allocation = all_sections['allocation_breakdown']
```

## Integration Example

Here's how to integrate the extractor into your workflow:

```python
from section_extractor import SectionExtractor

def process_analysis_response(analysis_response: str, email_to: str):
    """Process and send different sections via webhook."""
    extractor = SectionExtractor()

    # Extract allocation for email subject/summary
    allocation = extractor.extract_allocation_breakdown(
        analysis_response,
        include_justification=False
    )

    # Extract BUY recommendations for notification
    buy_recs = extractor.extract_stock_recommendations(
        analysis_response,
        recommendation_type='BUY'
    )

    # Format notification
    buy_summary = "\n".join([
        f"{rec['ticker']}: {rec['investment_amount']}"
        for rec in buy_recs
    ])

    # Extract risk warnings for alert
    warnings = extractor.extract_risk_warnings(analysis_response)
    risk_alert = "\n".join([f"⚠️ {w}" for w in warnings])

    # Send via webhook
    webhook_payload = {
        "email_to": email_to,
        "allocation_summary": allocation,
        "buy_recommendations": buy_summary,
        "risk_warnings": risk_alert,
        "full_analysis": analysis_response
    }

    return webhook_payload
```

## Working with HTML Conversion

If you're converting to HTML for email, extract sections first:

```python
from section_extractor import SectionExtractor

def create_html_email(analysis_response: str):
    extractor = SectionExtractor()

    # Extract sections
    portfolio = extractor.extract_section(analysis_response, 'portfolio_assessment')
    allocation = extractor.extract_allocation_breakdown(analysis_response)
    buy_recs = extractor.extract_stock_recommendations(analysis_response, 'BUY')
    warnings = extractor.extract_risk_warnings(analysis_response)

    # Build custom HTML
    html = f"""
    <html>
    <body>
        <h1>Portfolio Assessment</h1>
        <p>{portfolio}</p>

        <h2>Recommended Allocation</h2>
        <pre>{allocation}</pre>

        <h2>Buy Recommendations</h2>
        <ul>
            {''.join([f'<li><strong>{r["ticker"]}</strong>: {r["investment_amount"]}</li>' for r in buy_recs])}
        </ul>

        <h2>Risk Warnings</h2>
        <ul>
            {''.join([f'<li>{w}</li>' for w in warnings])}
        </ul>
    </body>
    </html>
    """

    return html
```

## Supported Section Keywords

The extractor recognizes these section keywords (case-insensitive):

- **PORTFOLIO ASSESSMENT** or **1. PORTFOLIO ASSESSMENT**
- **ALLOCATION BREAKDOWN** or **2. ALLOCATION BREAKDOWN**
- **INDIVIDUAL STOCK RECOMMENDATIONS** or **3. INDIVIDUAL STOCK RECOMMENDATIONS**
- **RISK WARNINGS** or **4. RISK WARNINGS**

## Error Handling

All extraction methods return `None` or empty lists if the section is not found:

```python
# Check if section exists
allocation = extractor.extract_allocation_breakdown(analysis_response)
if allocation:
    print(allocation)
else:
    print("Allocation breakdown not found")

# Risk warnings always returns a list (empty if not found)
warnings = extractor.extract_risk_warnings(analysis_response)
if warnings:
    for warning in warnings:
        print(warning)
else:
    print("No risk warnings found")
```

## Testing

Run the test script to see all extraction methods in action:

```bash
python test_extractor.py
```

This will demonstrate:
- Allocation extraction (with/without justification)
- Risk warnings extraction
- Stock recommendations filtering (BUY/HOLD/SELL)
- Portfolio assessment extraction
- All sections summary

## Key Benefits

✅ **No delimiter dependency** - Uses keyword-based section detection instead of `#` or `*`
✅ **Flexible filtering** - Filter recommendations by type (BUY/HOLD/SELL)
✅ **Structured data** - Returns Python dictionaries and lists for easy processing
✅ **Error resilient** - Handles missing sections gracefully
✅ **Easy integration** - Works seamlessly with your existing webhook/email flow

## Notes

- The extractor preserves the original formatting and indentation
- Works with both numbered (1., 2., 3.) and unnumbered section headers
- Case-insensitive keyword matching
- Handles multi-line content within sections
- Stops at the next section boundary automatically
