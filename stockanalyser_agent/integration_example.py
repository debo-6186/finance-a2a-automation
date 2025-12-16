"""
Integration example showing how to use SectionExtractor with the StockAnalyzerAgent.
This demonstrates how to extract and use specific sections from the analysis response.
"""
from section_extractor import SectionExtractor
import json


def example_webhook_payload_with_sections(analysis_response: str, email_to: str) -> dict:
    """
    Example: Create webhook payload with extracted sections.

    This shows how you might modify send_analysis_to_webhook to send
    more structured data instead of just the full text.
    """
    extractor = SectionExtractor()

    # Extract all sections
    sections = extractor.extract_all_sections(analysis_response)

    # Extract structured data
    allocation = extractor.extract_allocation_breakdown(analysis_response, include_justification=False)
    buy_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='BUY')
    hold_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='HOLD')
    sell_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='SELL')
    warnings = extractor.extract_risk_warnings(analysis_response)

    # Create structured payload
    payload = {
        "email_to": email_to,
        "full_analysis": analysis_response,  # Keep full text for email body

        # Structured sections for easy access
        "sections": {
            "portfolio_assessment": sections.get('portfolio_assessment'),
            "allocation_breakdown": allocation,
            "risk_warnings": warnings
        },

        # Categorized recommendations
        "recommendations": {
            "buy": [
                {
                    "ticker": rec['ticker'],
                    "amount": rec['investment_amount'],
                    "metrics": rec['key_metrics'],
                    "reasoning": rec['reasoning']
                }
                for rec in buy_recs
            ],
            "hold": [rec['ticker'] for rec in hold_recs],
            "sell": [
                {
                    "ticker": rec['ticker'],
                    "reasoning": rec['reasoning']
                }
                for rec in sell_recs
            ]
        },

        # Summary stats
        "summary": {
            "total_buy_recommendations": len(buy_recs),
            "total_hold_recommendations": len(hold_recs),
            "total_sell_recommendations": len(sell_recs),
            "total_risk_warnings": len(warnings)
        }
    }

    return payload


def example_send_email_notification(analysis_response: str, email_to: str) -> str:
    """
    Example: Send email with only BUY recommendations and allocation.

    This shows how you might create a concise email notification
    with just the actionable information.
    """
    extractor = SectionExtractor()

    # Extract only what we need
    allocation = extractor.extract_allocation_breakdown(analysis_response)
    buy_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='BUY')
    warnings = extractor.extract_risk_warnings(analysis_response)

    # Build email body
    email_body = f"""
Portfolio Investment Recommendations

{allocation}

BUY RECOMMENDATIONS ({len(buy_recs)} stocks):
"""

    for rec in buy_recs:
        email_body += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rec['ticker']} - {rec['investment_amount']}
{rec['key_metrics']}
{rec['reasoning']}
"""

    if warnings:
        email_body += f"""

⚠️ RISK WARNINGS:
"""
        for i, warning in enumerate(warnings, 1):
            email_body += f"{i}. {warning}\n"

    return email_body


def example_filter_high_conviction_buys(analysis_response: str) -> list:
    """
    Example: Filter BUY recommendations for high-conviction plays.

    This shows how to programmatically filter recommendations based on criteria.
    """
    extractor = SectionExtractor()

    # Get all BUY recommendations
    buy_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='BUY')

    # Filter for high conviction (look for "Strong Buy" in metrics)
    high_conviction = []
    for rec in buy_recs:
        if 'Strong Buy' in rec['key_metrics']:
            high_conviction.append(rec)

    return high_conviction


def example_create_investment_summary(analysis_response: str) -> dict:
    """
    Example: Create a concise investment summary dashboard.

    This shows how to create a summary for display in a UI or notification.
    """
    extractor = SectionExtractor()

    buy_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='BUY')
    hold_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='HOLD')
    sell_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='SELL')

    # Calculate total investment
    total_investment = 0
    for rec in buy_recs:
        amount_str = rec['investment_amount'].replace('$', '').replace(',', '')
        if amount_str:
            try:
                total_investment += float(amount_str)
            except ValueError:
                pass

    # Create summary
    summary = {
        "action_required": len(buy_recs) + len(sell_recs),
        "total_investment": f"${total_investment:,.2f}",
        "buy_count": len(buy_recs),
        "hold_count": len(hold_recs),
        "sell_count": len(sell_recs),
        "buy_tickers": [rec['ticker'] for rec in buy_recs],
        "sell_tickers": [rec['ticker'] for rec in sell_recs]
    }

    return summary


def example_generate_trading_checklist(analysis_response: str) -> list:
    """
    Example: Generate a checklist for executing trades.

    This shows how to create actionable items from the analysis.
    """
    extractor = SectionExtractor()

    buy_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='BUY')
    sell_recs = extractor.extract_stock_recommendations(analysis_response, recommendation_type='SELL')

    checklist = []

    # Add BUY actions
    for rec in buy_recs:
        checklist.append({
            "action": "BUY",
            "ticker": rec['ticker'],
            "amount": rec['investment_amount'],
            "status": "pending"
        })

    # Add SELL actions
    for rec in sell_recs:
        checklist.append({
            "action": "SELL",
            "ticker": rec['ticker'],
            "amount": "ALL",  # or calculate based on holdings
            "status": "pending"
        })

    return checklist


def example_risk_alert_check(analysis_response: str, risk_threshold: int = 2) -> dict:
    """
    Example: Check if risk warnings exceed threshold and create alert.

    This shows how to use risk warnings for automated alerts.
    """
    extractor = SectionExtractor()

    warnings = extractor.extract_risk_warnings(analysis_response)

    alert = {
        "risk_level": "HIGH" if len(warnings) >= risk_threshold else "NORMAL",
        "warning_count": len(warnings),
        "warnings": warnings,
        "requires_review": len(warnings) >= risk_threshold
    }

    return alert


# ============================================================================
# DEMONSTRATION
# ============================================================================

if __name__ == "__main__":
    # Sample analysis response (abbreviated)
    sample_response = """1. PORTFOLIO ASSESSMENT
The existing portfolio is heavily concentrated in the Information Technology and Communication Services sectors.

2. ALLOCATION BREAKDOWN - October 07, 2025
- NVDA: 25% ($400)
- MSFT: 25% ($400)
- META: 25% ($400)
- AVGO: 25% ($400)

Total: 100% ($1600)

Justification: Equal-weight allocation across high-conviction names.

3. INDIVIDUAL STOCK RECOMMENDATIONS

Ticker: NVDA
RECOMMENDATION: BUY
Investment Amount: $400
Key Metrics: Current P/E [52.8], Target Upside [16.0%], Analyst Rating [Strong Buy], Revenue Growth [55.6%]
Reasoning: NVDA meets all buy criteria with exceptional growth.

Ticker: TSLA
RECOMMENDATION: SELL
Key Metrics: Current P/E [263.3], Target Upside [-20.6%]
Reasoning: Tesla meets sell criteria due to negative growth and high valuation.

4. RISK WARNINGS
- High-Beta Stocks: NVDA (beta 2.12) exhibits higher volatility
- Valuation Risk: TSLA trades at exceptionally high P/E ratios"""

    print("=" * 80)
    print("SECTION EXTRACTOR INTEGRATION EXAMPLES")
    print("=" * 80)

    # Example 1: Structured webhook payload
    print("\n1. STRUCTURED WEBHOOK PAYLOAD:")
    print("-" * 80)
    payload = example_webhook_payload_with_sections(sample_response, "investor@example.com")
    print(json.dumps(payload['summary'], indent=2))
    print(f"\nBuy recommendations: {len(payload['recommendations']['buy'])}")
    print(f"Sell recommendations: {len(payload['recommendations']['sell'])}")

    # Example 2: Concise email notification
    print("\n2. CONCISE EMAIL NOTIFICATION:")
    print("-" * 80)
    email = example_send_email_notification(sample_response, "investor@example.com")
    print(email[:300] + "...")

    # Example 3: High conviction filter
    print("\n3. HIGH CONVICTION BUY RECOMMENDATIONS:")
    print("-" * 80)
    high_conviction = example_filter_high_conviction_buys(sample_response)
    for rec in high_conviction:
        print(f"  - {rec['ticker']}: {rec['investment_amount']}")

    # Example 4: Investment summary
    print("\n4. INVESTMENT SUMMARY:")
    print("-" * 80)
    summary = example_create_investment_summary(sample_response)
    print(json.dumps(summary, indent=2))

    # Example 5: Trading checklist
    print("\n5. TRADING CHECKLIST:")
    print("-" * 80)
    checklist = example_generate_trading_checklist(sample_response)
    for item in checklist:
        print(f"  [ ] {item['action']} {item['ticker']} - {item['amount']}")

    # Example 6: Risk alert
    print("\n6. RISK ALERT CHECK:")
    print("-" * 80)
    alert = example_risk_alert_check(sample_response, risk_threshold=2)
    print(json.dumps(alert, indent=2))
