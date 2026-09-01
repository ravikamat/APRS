from typing import Optional
from pydantic import BaseModel, Field

class ScoreBreakdown(BaseModel):
    """Data model for the score breakdown of a product opportunity."""
    market_signal: float = Field(description="Score for market signal based on BSR")
    review_quality: float = Field(description="Score for review quality based on rating and count")
    margin_safety: float = Field(description="Score for margin safety based on net margin percentage")
    defect_fixability: float = Field(description="Score based on whether the product has fixable defects")
    competition_density: float = Field(description="Score based on number of competitors")
    total: float = Field(description="Total aggregate score")
    verdict: str = Field(description="Final verdict: PROCEED, MARGINAL, or REJECT")

class ScoringEngine:
    """Deterministic scoring engine for evaluating e-commerce product opportunities."""
    
    def __init__(self):
        self.threshold_proceed = 75.0
        self.threshold_marginal = 60.0
   
    def score(self, bsr: Optional[int], rating: float, review_count: int,
              net_margin_pct: float, has_defects: bool,
              competitor_count: int = 10) -> ScoreBreakdown:
        """
        Calculate the opportunity score based on the rubric.
        """
        # 1. Market Signal (25 pts)
        if bsr is None:
            # 5.0 penalty from max if no BSR
            market_signal = 20.0
        else:
            market_signal = max(0.0, 25.0 - (bsr / 2000.0))
            market_signal = min(25.0, market_signal)
        market_signal = round(market_signal, 1)

        # 2. Review Quality (20 pts)
        if rating >= 4.2 and review_count >= 100:
            review_quality = 20.0
        elif rating >= 3.8 and review_count >= 50:
            review_quality = 12.0
        elif rating >= 3.5:
            review_quality = 5.0
        else:
            review_quality = 0.0
            
        # 3. Margin Safety (40 pts)
        if net_margin_pct >= 30.0:
            margin_safety = 40.0
        elif net_margin_pct >= 25.0:
            margin_safety = 32.0
        elif net_margin_pct >= 20.0:
            margin_safety = 24.0
        else:
            margin_safety = 0.0
            
        # 4. Defect Fixability (10 pts)
        if has_defects:
            defect_fixability = 10.0
        else:
            defect_fixability = 2.0
            
        # 5. Competition Density (5 pts)
        if competitor_count <= 5:
            competition_density = 5.0
        elif competitor_count <= 10:
            competition_density = 2.5
        else:
            competition_density = 0.0
            
        total = round(market_signal + review_quality + margin_safety + defect_fixability + competition_density, 1)
        
        # Determine verdict
        if total >= self.threshold_proceed:
            verdict = 'PROCEED'
        elif total >= self.threshold_marginal:
            verdict = 'MARGINAL'
        else:
            verdict = 'REJECT'
            
        return ScoreBreakdown(
            market_signal=market_signal,
            review_quality=review_quality,
            margin_safety=margin_safety,
            defect_fixability=defect_fixability,
            competition_density=competition_density,
            total=total,
            verdict=verdict
        )
