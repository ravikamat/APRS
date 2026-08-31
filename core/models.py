"""
core/models.py — Canonical Domain Entity Contracts for APRS V6 Pro.

Versioned Pydantic V2 schemas for:
- TrendSignal: Open-web trend evidence from social/search channels.
- MarketplaceListing: Cross-platform product listings (Amazon, Flipkart, Meesho, Shopify).
- CanonicalProduct: Master product record with demand proxy scoring.
- DefectCluster: Customer complaint clusters and v2.0 engineering specs.
- ScenarioEconomics: Detailed breakdown for a single scenario (Conservative / Expected / Upside).
- EconomicsAssessment: 15-factor 3-scenario unit economics dossier.
- NegativeFinding: Formal backtracking audit event for false-positive alerts.
- LaunchpadItem: Sourcing, QC AQL 2.5, and PO tracking entity.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import datetime


class TrendSignal(BaseModel):
    signal_id: Optional[int] = None
    platform: str = Field(..., description="Platform: instagram, tiktok, meta_ads, google_trends, reddit, youtube, web")
    keyword: str
    trend_category: str = "General"
    region: str = "India"
    search_volume_est: int = 0
    velocity_score: float = Field(default=75.0, ge=0.0, le=100.0)
    longevity_days: int = Field(default=14, ge=1)
    longevity_type: str = "EVERGREEN_PROBLEM_SOLVER"  # EVERGREEN_PROBLEM_SOLVER or FAD_SPIKE
    raw_signal_json: Dict[str, Any] = Field(default_factory=dict)
    status: str = "ACTIVE"
    created_at: Optional[str] = None


class MarketplaceListing(BaseModel):
    listing_id: Optional[int] = None
    product_id: str
    platform: str  # amazon, flipkart, meesho, myntra, shopify
    title: str
    price: float = Field(..., gt=0)
    currency: str = "INR"
    rating: Optional[float] = None
    review_count: int = 0
    listing_url: str
    seller_name: Optional[str] = None
    in_stock: int = 1
    rank_signal: Optional[int] = None
    extraction_confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class DefectCluster(BaseModel):
    cluster_id: Optional[int] = None
    product_id: str
    defect_type: str = "Structural / Material"
    customer_problem_statement: str
    frequency_estimate_pct: float = Field(default=15.0, ge=0.0, le=100.0)
    severity_score: float = Field(default=7.0, ge=1.0, le=10.0)
    platforms_seen: List[str] = Field(default_factory=list)
    root_cause_hypotheses: List[str] = Field(default_factory=list)
    proposed_v2_solution: str
    solution_feasibility_score: float = Field(default=85.0, ge=0.0, le=100.0)
    estimated_bom_cost_delta: float = 0.0
    fatal_hazard_detected: bool = False
    requires_engineering_validation: bool = False


class ScenarioEconomics(BaseModel):
    scenario_name: str  # Conservative, Expected, Upside
    planned_msrp: float
    fob_price: float
    landed_cogs: float
    gross_profit: float
    gross_margin_pct: float
    volumetric_freight_cost: float
    marketplace_commission: float
    fulfillment_fee: float
    payment_or_cod_fee: float
    rto_reserve: float
    return_fraud_reserve: float
    ad_tacos_reserve: float
    net_tax_burden: float
    total_variable_cost: float
    net_profit: float
    net_profit_pct: float
    contribution_margin: float
    first_batch_capital: float
    status: str  # PASS or FAIL


class EconomicsAssessment(BaseModel):
    product_id: str
    region: str
    currency: str = "INR"
    conservative: ScenarioEconomics
    expected: ScenarioEconomics
    upside: ScenarioEconomics
    lead_time_days: int = 30
    trend_half_life_days: int = 90
    lead_time_risk_factor: float = 0.0
    is_financially_viable: bool = True
    composite_score: float = Field(default=80.0, ge=0.0, le=100.0)
    recommendation: str = "PASS"


class NegativeFinding(BaseModel):
    finding_id: Optional[int] = None
    product_id: str
    origin_stage: str  # trend_scout, marketplace_harvester, defect_analyst, economics_auditor, chief_arbiter
    target_stage: str  # previous stage to backtrack to
    reason_code: str   # FAD_SPIKE, FATAL_FLAW_OR_IP_RISK, MARGIN_FAIL, HIGH_RTO_RISK, LEAD_TIME_DECAY
    human_readable_reason: str
    evidence_summary: str = ""
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM
    recommended_action: str = "Branch to next variant / candidate"
    created_at: Optional[str] = None


class LaunchpadItem(BaseModel):
    item_id: Optional[int] = None
    product_id: str
    product_name: str
    target_launch_date: Optional[str] = None
    target_moq: int = 300
    target_fob: float = 0.0
    confirmed_factory_name: Optional[str] = None
    sample_ordered: bool = False
    sample_approved: bool = False
    qc_aql_standard: str = "ISO 2859-1 (AQL 2.5 Major / 4.0 Minor)"
    compliance_checklist_passed: bool = False
    purchase_order_generated: bool = False
    launch_status: str = "SOURCING_NEGOTIATION"  # SOURCING_NEGOTIATION, SAMPLING, QC_INSPECTION, READY_FOR_PO, LAUNCHED
