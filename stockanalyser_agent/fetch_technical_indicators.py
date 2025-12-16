"""
Fetch technical indicators for a given stock ticker using Perplexity API.
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from perplexity import Perplexity
from typing import Dict, Optional

# Load environment variables from .env file
load_dotenv()

def fetch_technical_indicators(
    ticker: str,
    model: str = "sonar-pro"
) -> Dict:
    """
    Fetch comprehensive technical indicators for a given stock ticker using Perplexity API.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'TSLA')
        model: Perplexity model to use (default: "sonar-pro")

    Returns:
        Dict containing technical indicators in JSON format

    Raises:
        ValueError: If ticker is invalid
        Exception: If API call fails
    """
    # Validate ticker input
    if not ticker or not isinstance(ticker, str):
        raise ValueError("Ticker must be a non-empty string")

    ticker = ticker.upper().strip()

    # Initialize Perplexity client
    client = Perplexity(api_key=os.getenv("PERPLEXITY_API_KEY"))
    print(f"Using Perplexity API for technical indicators of {ticker}")

    # System prompt for technical analysis
    system_prompt = """You are a technical analysis expert specializing in stock market indicators.
Your task is to provide comprehensive technical indicators for the requested stock ticker.

IMPORTANT: Return ONLY valid JSON with no additional text, markdown, or code blocks.

The response MUST include the following technical indicators in this exact JSON structure:
{
    "ticker": "string (stock ticker symbol)",
    "timestamp": "string (current date/time)",
    "moving_averages": {
        "sma_50": "string (50-day Simple Moving Average)",
        "sma_200": "string (200-day Simple Moving Average)",
        "ema_12": "string (12-day Exponential Moving Average)",
        "ema_26": "string (26-day Exponential Moving Average)"
    },
    "momentum_indicators": {
        "rsi_14": "string (14-day Relative Strength Index)",
        "macd": {
            "macd_line": "string",
            "signal_line": "string",
            "histogram": "string"
        },
        "stochastic": {
            "k_line": "string",
            "d_line": "string"
        }
    },
    "volatility_indicators": {
        "bollinger_bands": {
            "upper_band": "string",
            "middle_band": "string",
            "lower_band": "string"
        },
        "atr_14": "string (14-day Average True Range)"
    },
    "volume_indicators": {
        "obv": "string (On-Balance Volume)",
        "volume_sma_20": "string (20-day Volume Moving Average)"
    },
    "trend_indicators": {
        "adx_14": "string (14-day Average Directional Index)",
        "cci_20": "string (20-day Commodity Channel Index)",
        "williams_r": "string (Williams %R)"
    },
    "price_levels": {
        "current_price": "string",
        "52_week_high": "string",
        "52_week_low": "string",
        "support_level": "string",
        "resistance_level": "string"
    },
    "technical_summary": {
        "overall_trend": "string (Bullish/Bearish/Neutral)",
        "buy_signals": "number (count of bullish indicators)",
        "sell_signals": "number (count of bearish indicators)",
        "neutral_signals": "number (count of neutral indicators)",
        "recommendation": "string (Strong Buy/Buy/Hold/Sell/Strong Sell)"
    }
}

RULES:
- Use the most recent market data available
- Use internet search to get the latest market data
- All numeric values should be formatted as strings with appropriate precision
- Include the timestamp of when the analysis was performed
- Provide actual calculated values based on real market data, not placeholders
- The overall recommendation should be based on the confluence of technical indicators"""

    # User prompt requesting technical indicators
    user_prompt = f"""Provide comprehensive technical indicators for stock ticker: {ticker}
Today's date is {datetime.now().strftime("%Y-%m-%d")}
Include all the technical indicators specified with their current calculated values.
Return ONLY valid JSON with no additional text, markdown, or code blocks."""

    try:
        # Call Perplexity API
        completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            model=model
        )

        # Extract and parse the response
        response_text = completion.choices[0].message.content

        if response_text:
            # Clean the response text (remove any markdown code blocks if present)
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            # Parse JSON
            indicators_data = json.loads(cleaned_text)
            print(f"Successfully fetched technical indicators for {ticker}")
            return indicators_data
        else:
            raise Exception("Empty response from Perplexity API")

    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse JSON response: {str(e)}")
    except Exception as e:
        raise Exception(f"Error fetching technical indicators: {str(e)}")


def main():
    """
    Example usage of the fetch_technical_indicators function.
    """
    # Example: Fetch technical indicators for Apple stock
    ticker = "AAPL"

    try:
        print(f"\nFetching technical indicators for {ticker}...")
        indicators = fetch_technical_indicators(ticker)

        # Pretty print the JSON response
        print("\n" + "="*60)
        print(f"TECHNICAL INDICATORS FOR {ticker}")
        print("="*60)
        print(json.dumps(indicators, indent=2))
        print("="*60 + "\n")

        # Save to file
        output_file = f"{ticker}_technical_indicators.json"
        with open(output_file, 'w') as f:
            json.dump(indicators, f, indent=2)
        print(f"Results saved to: {output_file}")

    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    import sys

    # Check if ticker provided as command line argument
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        try:
            print(f"\nFetching technical indicators for {ticker}...")
            indicators = fetch_technical_indicators(ticker)
            print(json.dumps(indicators, indent=2))
        except Exception as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            sys.exit(1)
    else:
        # Run the example
        sys.exit(main())
