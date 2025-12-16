"""
Section Extractor for Portfolio Analysis
Extracts specific sections from analysis response using keyword-based filtering.
"""
import re
from typing import Dict, List, Optional


class SectionExtractor:
    """Extracts sections from portfolio analysis using keyword-based filtering."""

    # Define section keywords and their variations
    SECTION_KEYWORDS = {
        'portfolio_assessment': ['PORTFOLIO ASSESSMENT', '1. PORTFOLIO ASSESSMENT'],
        'allocation_breakdown': ['ALLOCATION BREAKDOWN', '2. ALLOCATION BREAKDOWN'],
        'individual_recommendations': ['INDIVIDUAL STOCK RECOMMENDATIONS', '3. INDIVIDUAL STOCK RECOMMENDATIONS'],
        'risk_warnings': ['RISK WARNINGS', '4. RISK WARNINGS']
    }

    @staticmethod
    def normalize_text(text: str) -> str:
        """Remove extra whitespace and normalize line endings."""
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def find_section_boundaries(text: str, keyword: str, next_keywords: List[str]) -> Optional[tuple]:
        """
        Find the start and end positions of a section based on keyword.

        Args:
            text: The full analysis text
            keyword: The keyword that marks the start of the section
            next_keywords: List of keywords that could mark the end of the section

        Returns:
            Tuple of (start_position, end_position) or None if not found
        """
        # Find start position
        start_match = re.search(re.escape(keyword), text, re.IGNORECASE)
        if not start_match:
            return None

        start_pos = start_match.start()

        # Find end position by looking for the next section keyword
        end_pos = len(text)
        for next_keyword in next_keywords:
            next_match = re.search(re.escape(next_keyword), text[start_pos + len(keyword):], re.IGNORECASE)
            if next_match:
                end_pos = min(end_pos, start_pos + len(keyword) + next_match.start())

        return (start_pos, end_pos)

    @classmethod
    def extract_section(cls, text: str, section_name: str) -> Optional[str]:
        """
        Extract a specific section from the analysis text.

        Args:
            text: The full analysis response text
            section_name: Name of the section to extract (e.g., 'allocation_breakdown')

        Returns:
            Extracted section text or None if not found
        """
        # Get keywords for this section
        keywords = cls.SECTION_KEYWORDS.get(section_name)
        if not keywords:
            return None

        # Try each keyword variation
        for keyword in keywords:
            # Build list of all other section keywords (for finding end boundary)
            all_other_keywords = []
            for other_section, other_keywords in cls.SECTION_KEYWORDS.items():
                if other_section != section_name:
                    all_other_keywords.extend(other_keywords)

            # Find section boundaries
            boundaries = cls.find_section_boundaries(text, keyword, all_other_keywords)
            if boundaries:
                start_pos, end_pos = boundaries
                section_text = text[start_pos:end_pos].strip()
                return section_text

        return None

    @classmethod
    def extract_all_sections(cls, text: str) -> Dict[str, Optional[str]]:
        """
        Extract all sections from the analysis text.

        Args:
            text: The full analysis response text

        Returns:
            Dictionary mapping section names to their extracted content
        """
        sections = {}
        for section_name in cls.SECTION_KEYWORDS.keys():
            sections[section_name] = cls.extract_section(text, section_name)

        return sections

    @classmethod
    def extract_allocation_breakdown(cls, text: str, include_justification: bool = True) -> Optional[str]:
        """
        Extract the allocation breakdown section with special formatting.

        Args:
            text: The full analysis response text
            include_justification: Whether to include justification text

        Returns:
            Formatted allocation breakdown or None if not found
        """
        section = cls.extract_section(text, 'allocation_breakdown')
        if not section:
            return None

        # Extract bullet points and format them
        lines = section.split('\n')
        formatted_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip the header line
            if 'ALLOCATION BREAKDOWN' in line:
                formatted_lines.append(line)
                continue

            # Skip justification if not requested
            if not include_justification and 'Justification:' in line:
                break

            # Keep bullet points and important lines
            if line.startswith('-') or line.startswith('Total:') or 'Justification:' in line:
                formatted_lines.append(line)

        return '\n'.join(formatted_lines)

    @classmethod
    def extract_risk_warnings(cls, text: str) -> List[str]:
        """
        Extract risk warnings as a list of individual warnings.

        Args:
            text: The full analysis response text

        Returns:
            List of individual risk warning strings
        """
        section = cls.extract_section(text, 'risk_warnings')
        if not section:
            return []

        # Extract bullet points
        warnings = []
        lines = section.split('\n')

        for line in lines:
            line = line.strip()
            # Skip header and empty lines
            if not line or 'RISK WARNINGS' in line:
                continue

            # Extract bullet points
            if line.startswith('-'):
                warning = line.lstrip('-').strip()
                warnings.append(warning)

        return warnings

    @classmethod
    def extract_stock_recommendations(cls, text: str, recommendation_type: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Extract individual stock recommendations.

        Args:
            text: The full analysis response text
            recommendation_type: Filter by type ('BUY', 'HOLD', 'SELL') or None for all

        Returns:
            List of dictionaries containing stock recommendation details
        """
        section = cls.extract_section(text, 'individual_recommendations')
        if not section:
            return []

        recommendations = []
        lines = section.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Detect start of a stock recommendation
            if line.startswith('Ticker:'):
                # Parse ticker and recommendation
                ticker_match = re.search(r'Ticker:\s*(\w+)', line)

                if ticker_match:
                    ticker = ticker_match.group(1)

                    # Initialize the stock entry
                    current_stock = {
                        'ticker': ticker,
                        'recommendation': '',
                        'investment_amount': '',
                        'key_metrics': '',
                        'reasoning': ''
                    }

                    # Collect the following lines for this stock
                    i += 1
                    while i < len(lines):
                        detail_line = lines[i].strip()

                        # Check if we've hit the next ticker
                        if detail_line.startswith('Ticker:'):
                            break

                        # Check if line is empty
                        if not detail_line:
                            i += 1
                            continue

                        # Parse RECOMMENDATION line
                        if detail_line.startswith('RECOMMENDATION:'):
                            rec_match = re.search(r'(BUY|HOLD|SELL)', detail_line)
                            if rec_match:
                                current_stock['recommendation'] = rec_match.group(1)
                        elif detail_line.startswith('Investment Amount:'):
                            current_stock['investment_amount'] = detail_line.replace('Investment Amount:', '').strip()
                        elif detail_line.startswith('Key Metrics:'):
                            current_stock['key_metrics'] = detail_line.replace('Key Metrics:', '').strip()
                        elif detail_line.startswith('Reasoning:'):
                            current_stock['reasoning'] = detail_line.replace('Reasoning:', '').strip()
                        elif current_stock['reasoning'] and not any(detail_line.startswith(x) for x in ['Ticker:', 'RECOMMENDATION:', 'Investment Amount:', 'Key Metrics:']):
                            # Continue reasoning from previous line
                            current_stock['reasoning'] += ' ' + detail_line

                        i += 1

                    # Filter by recommendation type if specified
                    if recommendation_type is None or current_stock['recommendation'] == recommendation_type.upper():
                        recommendations.append(current_stock)
                    continue

            i += 1

        return recommendations


# Example usage and testing
if __name__ == "__main__":
    # Test with sample data
    sample_text = """1. PORTFOLIO ASSESSMENT
The existing portfolio is heavily concentrated in the Information Technology and Communication Services sectors, reflecting a high-growth, tech-focused investment strategy.

2. ALLOCATION BREAKDOWN - October 07, 2025
- NVDA: 25% ($400)
- MSFT: 25% ($400)
- META: 25% ($400)
- AVGO: 25% ($400)

Total: 100% ($1600)

Justification: This equal-weight allocation across four high-conviction names maintains the portfolio's existing pattern.

3. INDIVIDUAL STOCK RECOMMENDATIONS

Ticker: NVDA
RECOMMENDATION: BUY
Investment Amount: $400
Key Metrics: Current P/E [52.8], Target Upside [16.0%]
Reasoning: NVDA meets all buy criteria with exceptional revenue and earnings growth.

Ticker: GOOGL
RECOMMENDATION: HOLD
Key Metrics: Current P/E [26.3], Target Upside [-0.8%]
Reasoning: GOOGL is a hold due to mixed signals.

4. RISK WARNINGS
- High-Beta Stocks: NVDA (beta 2.12) exhibits significantly higher volatility
- Sector Concentration: The portfolio remains heavily concentrated"""

    # Test extraction
    extractor = SectionExtractor()

    # Extract all sections
    print("=== ALL SECTIONS ===")
    sections = extractor.extract_all_sections(sample_text)
    for name, content in sections.items():
        print(f"\n{name.upper()}:")
        print(content[:100] if content else "Not found")

    # Extract allocation breakdown
    print("\n\n=== ALLOCATION BREAKDOWN ===")
    allocation = extractor.extract_allocation_breakdown(sample_text)
    print(allocation)

    # Extract risk warnings
    print("\n\n=== RISK WARNINGS ===")
    warnings = extractor.extract_risk_warnings(sample_text)
    for warning in warnings:
        print(f"- {warning}")

    # Extract BUY recommendations only
    print("\n\n=== BUY RECOMMENDATIONS ===")
    buy_recs = extractor.extract_stock_recommendations(sample_text, recommendation_type='BUY')
    for rec in buy_recs:
        print(f"Ticker: {rec['ticker']}")
        print(f"Amount: {rec['investment_amount']}")
        print(f"Reasoning: {rec['reasoning'][:100]}...")
