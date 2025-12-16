"""
Test script to demonstrate section extraction from portfolio analysis.
"""
from section_extractor import SectionExtractor

# Your actual data
analysis_response = """1. PORTFOLIO ASSESSMENT
The existing portfolio is heavily concentrated in the Information Technology and Communication Services sectors, reflecting a high-growth, tech-focused investment strategy. While this has likely driven strong performance, it also presents significant concentration risk, making the portfolio sensitive to downturns in these specific sectors.

2. ALLOCATION BREAKDOWN - October 07, 2025
- NVDA: 25% ($400)
- MSFT: 25% ($400)
- META: 25% ($400)
- AVGO: 25% ($400)

Total: 100% ($1600)

Justification: This equal-weight allocation across four high-conviction names maintains the portfolio's existing pattern of concentration in Information Technology and Communication Services. Each stock meets the stringent buy criteria, and an equal allocation diversifies company-specific risk while deploying the full budget into compelling growth opportunities.

3. INDIVIDUAL STOCK RECOMMENDATIONS

Ticker: NVDA
RECOMMENDATION: BUY
Investment Amount: $400
Key Metrics: Current P/E [52.8], Target Upside [16.0%], Analyst Rating [Strong Buy], Revenue Growth [55.6%]
Reasoning: NVDA meets all buy criteria with exceptional revenue and earnings growth (>50%), a strong analyst consensus, and significant price upside. The stock shows positive technical momentum, trading above its 50-day moving average, reinforcing its position as a leader in the high-growth AI space.

Ticker: MSFT
RECOMMENDATION: BUY
Investment Amount: $400
Key Metrics: Current P/E [38.4], Target Upside [18.4%], Analyst Rating [Strong Buy], Revenue Growth [18.1%]
Reasoning: Microsoft qualifies as a buy due to its strong fundamentals, including earnings growth over 20% and a potential 18.4% upside to the mean analyst target. The stock exhibits positive technical momentum above its 50-day MA and maintains a "Strong Buy" consensus, making it a core growth holding.

Ticker: META
RECOMMENDATION: BUY
Investment Amount: $400
Key Metrics: Current P/E [25.8], Target Upside [22.2%], Analyst Rating [Strong Buy], Revenue Growth [21.6%]
Reasoning: META is a compelling buy opportunity, featuring strong revenue and earnings growth (>20%), a significant 22.2% upside to analyst targets, and a reasonable P/E ratio. While the price is slightly below its 50-day MA, it remains above its 200-day MA, indicating a strong underlying trend that presents an attractive entry point.

Ticker: AVGO
RECOMMENDATION: BUY
Investment Amount: $400
Key Metrics: Current P/E [84.6], Target Upside [12.6%], Analyst Rating [Strong Buy], Revenue Growth [16.4%]
Reasoning: Broadcom is recommended as a buy based on its phenomenal earnings growth (188.1%), a "Strong Buy" analyst rating, and a 12.6% upside to its mean price target. The stock's price is above its 50-day moving average, confirming positive momentum and its fit within the portfolio's semiconductor focus.

Ticker: VOO
RECOMMENDATION: HOLD
Key Metrics: N/A (ETF)
Reasoning: As a core S&P 500 ETF, VOO provides essential market diversification. It is trading with positive momentum above its key moving averages and should be held as a foundational, stabilizing position in this tech-heavy portfolio.

Ticker: GOOGL
RECOMMENDATION: HOLD
Key Metrics: Current P/E [26.3], Target Upside [-0.8%], Analyst Rating [Buy], Revenue Growth [13.8%]
Reasoning: GOOGL is a hold due to mixed signals. While it has strong earnings growth (>20%) and positive momentum, its current price is slightly above the mean analyst price target, failing to offer the required ≥10% upside for a buy rating.

Ticker: NFLX
RECOMMENDATION: HOLD
Key Metrics: Current P/E [50.9], Target Upside [13.6%], Analyst Rating [Buy], Revenue Growth [15.9%]
Reasoning: Netflix is rated a hold because it fails to meet all buy criteria, specifically showing negative short-term momentum with its price below the 50-day moving average. Although it has strong earnings growth and sufficient price target upside, the mixed technical picture warrants a hold.

Ticker: AMZN
RECOMMENDATION: HOLD
Key Metrics: Current P/E [33.7], Target Upside [20.5%], Analyst Rating [Strong Buy], Revenue Growth [13.3%]
Reasoning: Amazon presents a mixed case and is therefore a hold. It boasts strong earnings growth and significant upside to its price target, but the stock is currently trading below its 50-day moving average, indicating negative short-term momentum.

Ticker: AAPL
RECOMMENDATION: HOLD
Key Metrics: Current P/E [38.8], Target Upside [-3.7%], Analyst Rating [Buy], Revenue Growth [9.6%]
Reasoning: Apple is a hold as it is currently trading above the mean analyst price target and its revenue/earnings growth is below the 20% threshold for a buy. Despite positive price momentum, the lack of clear value or high growth at this price point justifies a hold.

Ticker: SPOT
RECOMMENDATION: HOLD
Key Metrics: Current P/E [148.1], Target Upside [10.3%], Analyst Rating [Buy], Revenue Growth [10.1%]
Reasoning: Spotify is a hold due to its extremely high P/E ratio, modest revenue growth below 20%, and negative price momentum. While it just meets the 10% upside threshold, the combination of weak fundamentals and negative technicals prevents a buy recommendation.

Ticker: TSM
RECOMMENDATION: HOLD
Key Metrics: Current P/E [32.4], Target Upside [1.5%], Analyst Rating [Strong Buy], Revenue Growth [38.6%]
Reasoning: TSM is a hold because its current price is trading very close to the mean analyst target, offering minimal upside. Although its fundamental growth is exceptional and momentum is positive, it fails the valuation component of the buy criteria.

Ticker: TSLA
RECOMMENDATION: SELL
Key Metrics: Current P/E [263.3], Target Upside [-20.6%], Analyst Rating [Hold], Revenue Growth [-11.8%]
Reasoning: Tesla meets the criteria for a sell recommendation due to its combination of negative revenue and earnings growth alongside an extremely high P/E ratio of over 260. Furthermore, the current stock price is more than 20% above the mean analyst price target, indicating significant overvaluation.

4. RISK WARNINGS
- High-Beta Stocks: NVDA (beta 2.12) and TSLA (beta 2.09) exhibit significantly higher volatility than the overall market, which can lead to larger price swings.
- Valuation Risk: TSLA and SPOT trade at exceptionally high P/E ratios (263.3 and 148.1, respectively), making them vulnerable to sharp declines if growth expectations are not met. TSLA's negative growth makes this risk particularly acute.
- Sector Concentration: The recommended portfolio remains heavily concentrated in the Information Technology and Communication Services sectors. Any market rotation away from technology could cause this portfolio to underperform the broader market."""


def main():
    """Demonstrate section extraction functionality."""
    extractor = SectionExtractor()

    print("=" * 80)
    print("SECTION EXTRACTION DEMO")
    print("=" * 80)

    # 1. Extract ALLOCATION BREAKDOWN only
    print("\n1. ALLOCATION BREAKDOWN (without Justification):")
    print("-" * 80)
    allocation = extractor.extract_allocation_breakdown(analysis_response, include_justification=False)
    if allocation:
        print(allocation)
    else:
        print("Not found")

    # 2. Extract ALLOCATION BREAKDOWN with Justification
    print("\n2. ALLOCATION BREAKDOWN (with Justification):")
    print("-" * 80)
    allocation_full = extractor.extract_allocation_breakdown(analysis_response, include_justification=True)
    if allocation_full:
        print(allocation_full)
    else:
        print("Not found")

    # 3. Extract RISK WARNINGS as a list
    print("\n3. RISK WARNINGS (as list):")
    print("-" * 80)
    warnings = extractor.extract_risk_warnings(analysis_response)
    for i, warning in enumerate(warnings, 1):
        print(f"{i}. {warning}")

    # 4. Extract only BUY recommendations
    print("\n4. BUY RECOMMENDATIONS ONLY:")
    print("-" * 80)
    buy_recommendations = extractor.extract_stock_recommendations(analysis_response, recommendation_type='BUY')
    for rec in buy_recommendations:
        print(f"\nTicker: {rec['ticker']}")
        print(f"Recommendation: {rec['recommendation']}")
        print(f"Investment Amount: {rec['investment_amount']}")
        print(f"Key Metrics: {rec['key_metrics']}")
        print(f"Reasoning: {rec['reasoning']}")

    # 5. Extract only HOLD recommendations
    print("\n5. HOLD RECOMMENDATIONS ONLY:")
    print("-" * 80)
    hold_recommendations = extractor.extract_stock_recommendations(analysis_response, recommendation_type='HOLD')
    print(f"Found {len(hold_recommendations)} HOLD recommendations:")
    for rec in hold_recommendations:
        print(f"  - {rec['ticker']}")

    # 6. Extract only SELL recommendations
    print("\n6. SELL RECOMMENDATIONS ONLY:")
    print("-" * 80)
    sell_recommendations = extractor.extract_stock_recommendations(analysis_response, recommendation_type='SELL')
    print(f"Found {len(sell_recommendations)} SELL recommendations:")
    for rec in sell_recommendations:
        print(f"  - {rec['ticker']}: {rec['reasoning']}")

    # 7. Extract PORTFOLIO ASSESSMENT
    print("\n7. PORTFOLIO ASSESSMENT:")
    print("-" * 80)
    portfolio_assessment = extractor.extract_section(analysis_response, 'portfolio_assessment')
    if portfolio_assessment:
        print(portfolio_assessment)
    else:
        print("Not found")

    # 8. Extract all sections at once
    print("\n8. ALL SECTIONS SUMMARY:")
    print("-" * 80)
    all_sections = extractor.extract_all_sections(analysis_response)
    for section_name, content in all_sections.items():
        if content:
            print(f"\n{section_name.upper()}: {len(content)} characters")
        else:
            print(f"\n{section_name.upper()}: Not found")


if __name__ == "__main__":
    main()
