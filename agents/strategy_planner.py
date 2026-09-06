"""
agents/strategy_planner.py — Strategic Research Brain.

Weekly: Analyzes learned_rules + negative_findings + launchpad_outcomes + trend_signals
→ decides which categories/regions to research next.
Writes research_directive rows that drive all downstream agents.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from core.database import (
    get_connection, record_dynamic_niche, get_dynamic_niches,
    get_learned_rules, get_negative_findings, get_launchpad_items,
    get_trend_signals, get_active_trend_signals
)
from core.contracts import REGISTRY

logger = logging.getLogger("aprs.strategy_planner")


@dataclass
class ResearchDirective:
    """A strategic directive for where to hunt next."""
    category: str
    region: str
    priority_score: float
    rationale: str
    source_data: dict
    expires_at: str


class StrategyPlanner:
    """
    Strategic Research Brain — decides WHERE to look, not just how.
    
    Runs weekly (or on demand) to analyze:
    - learned_rules: What patterns led to wins/losses
    - negative_findings: What categories/products consistently fail
    - launchpad_outcomes: Real sales/margin data from launched products
    - trend_signals: Emerging trends from open-web scouting
    
    Outputs: research_directives table entries that all agents read first.
    """
    
    def __init__(self):
        self.conn = None
    
    def _get_connection(self):
        if self.conn is None:
            from core.database import get_connection
            self.conn = get_connection()
        return self.conn
    
    def analyze_learned_patterns(self) -> Dict[str, Any]:
        """Extract actionable patterns from learned_rules."""
        rules = get_learned_rules(active_only=True)
        
        patterns = {
            "winning_categories": {},
            "losing_categories": {},
            "winning_regions": {},
            "losing_regions": {},
            "successful_defect_types": [],
            "successful_price_bands": [],
        }
        
        for rule in rules:
            rule_type = rule.get("rule_type", "")
            category = rule.get("category", "").lower()
            region = rule.get("region", "").lower()
            params = rule.get("parameters", {})
            weight = rule.get("weight", 1.0)
            
            if "win" in rule_type or "proceed" in rule_type or "pass" in rule_type:
                patterns["winning_categories"][category] = patterns["winning_categories"].get(category, 0) + weight
                patterns["winning_regions"][region] = patterns["winning_regions"].get(region, 0) + weight
                if "defect" in str(params).lower():
                    patterns["successful_defect_types"].append(params)
                if "price" in str(params).lower() or "margin" in str(params).lower():
                    patterns["successful_price_bands"].append(params)
            elif "fail" in rule_type or "reject" in rule_type:
                patterns["losing_categories"][category] = patterns["losing_categories"].get(category, 0) + weight
                patterns["losing_regions"][region] = patterns["losing_regions"].get(region, 0) + weight
        
        return patterns
    
    def analyze_negative_findings(self) -> Dict[str, Any]:
        """Extract categories/products that consistently fail gates."""
        findings = get_negative_findings(limit=200)
        
        category_failures = {}
        gate_failures = {}
        reason_counts = {}
        
        for f in findings:
            cat = f.get("category", "").lower()
            gate = f.get("gate_number", 0)
            reason = f.get("reason", "")
            
            category_failures[cat] = category_failures.get(cat, 0) + 1
            gate_failures[gate] = gate_failures.get(gate, 0) + 1
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        # Sort by frequency
        top_avoid = sorted(category_failures.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "avoid_categories": [c for c, _ in top_avoid],
            "gate_failure_distribution": gate_failures,
            "top_reasons": sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        }
    
    def analyze_launchpad_outcomes(self) -> Dict[str, Any]:
        """Analyze real outcomes from launched products."""
        from core.database import get_connection
        conn = self._get_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT lo.*, mp.category, mp.region
            FROM launchpad_outcomes lo
            JOIN master_products mp ON lo.product_id = mp.product_id
            WHERE lo.recorded_at > datetime('now', '-90 days')
        ''')
        outcomes = [dict(r) for r in cur.fetchall()]
        
        if not outcomes:
            return {"message": "No launchpad outcomes yet - need live products first"}
        
        # Aggregate by category/region
        category_performance = {}
        region_performance = {}
        
        for o in outcomes:
            cat = o.get("category", "").lower()
            region = o.get("region", "").lower()
            sales = o.get("actual_monthly_sales", 0)
            margin = o.get("actual_net_margin_pct", 0)
            returns = o.get("actual_return_rate_pct", 0)
            roas = o.get("actual_ad_roas", 0)
            
            if cat not in category_performance:
                category_performance[cat] = {"sales": [], "margin": [], "returns": [], "roas": [], "count": 0}
            category_performance[cat]["sales"].append(sales)
            category_performance[cat]["margin"].append(margin)
            category_performance[cat]["returns"].append(returns)
            category_performance[cat]["roas"].append(roas)
            category_performance[cat]["count"] += 1
            
            if region not in region_performance:
                region_performance[region] = {"sales": [], "margin": [], "returns": [], "roas": [], "count": 0}
            region_performance[region]["sales"].append(sales)
            region_performance[region]["margin"].append(margin)
            region_performance[region]["returns"].append(returns)
            region_performance[region]["roas"].append(roas)
            region_performance[region]["count"] += 1
        
        # Compute averages
        def avg(lst): return sum(lst) / len(lst) if lst else 0
        
        cat_scores = {}
        for cat, data in category_performance.items():
            cat_scores[cat] = {
                "avg_sales": avg(data["sales"]),
                "avg_margin": avg(data["margin"]),
                "avg_returns": avg(data["returns"]),
                "avg_roas": avg(data["roas"]),
                "sample_size": data["count"],
                "composite": avg(data["sales"]) * 0.3 + avg(data["margin"]) * 0.4 + (100 - avg(data["returns"])) * 0.2 + min(avg(data["roas"]), 10) * 0.1
            }
        
        return {
            "category_performance": cat_scores,
            "region_performance": region_performance,
            "total_products": len(outcomes),
        }
    
    def analyze_trend_signals(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get high-velocity trend signals from recent scouting."""
        signals = get_active_trend_signals(region="India", limit=50)
        
        # Filter to recent high-velocity signals
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_signals = []
        
        for s in signals:
            try:
                created = datetime.fromisoformat(s.get("created_at", "").replace("Z", "+00:00"))
                if created > cutoff and s.get("velocity_score", 0) >= 70:
                    recent_signals.append(s)
            except:
                pass
        
        return sorted(recent_signals, key=lambda x: x.get("velocity_score", 0), reverse=True)[:20]
    
    def generate_directives(self, max_directives: int = 10) -> List[ResearchDirective]:
        """Generate research directives based on all analyses."""
        logger.info("Generating research directives...")
        
        learned = self.analyze_learned_patterns()
        negative = self.analyze_negative_findings()
        outcomes = self.analyze_launchpad_outcomes()
        trends = self.analyze_trend_signals()
        
        directives = []
        
        # 1. Directives from winning categories (exploit)
        for cat, score in sorted(learned["winning_categories"].items(), key=lambda x: x[1], reverse=True)[:3]:
            if cat not in negative["avoid_categories"]:
                directives.append(ResearchDirective(
                    category=cat.title(),
                    region="India",
                    priority_score=min(90, 60 + score * 5),
                    rationale=f"Winning category from learned rules (weight: {score:.1f}). Avoid categories: {negative['avoid_categories'][:3]}",
                    source_data={"type": "learned_win", "category_score": score, "avoid_list": negative["avoid_categories"][:5]},
                    expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                ))
        
        # 2. Directives from launchpad outcomes (real data)
        if "category_performance" in outcomes:
            for cat, perf in sorted(outcomes["category_performance"].items(), key=lambda x: x[1]["composite"], reverse=True)[:3]:
                if perf["sample_size"] >= 2 and cat not in negative["avoid_categories"]:
                    directives.append(ResearchDirective(
                        category=cat.title(),
                        region="India",
                        priority_score=min(95, 70 + perf["composite"] * 0.5),
                        rationale=f"Strong real-world performance: avg margin {perf['avg_margin']:.1f}%, sales {perf['avg_sales']:.0f}/mo, ROAS {perf['avg_roas']:.1f}",
                        source_data={"type": "launchpad_outcome", "performance": perf},
                        expires_at=(datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
                    ))
        
        # 3. Directives from trend signals (explore)
        for signal in trends[:5]:
            # Extract category from keyword
            kw = signal.get("keyword", "").lower()
            category = self._extract_category_from_keyword(kw)
            
            if category and category not in negative["avoid_categories"]:
                directives.append(ResearchDirective(
                    category=category.title(),
                    region=signal.get("region", "India"),
                    priority_score=min(85, 50 + signal.get("velocity_score", 70) * 0.3),
                    rationale=f"Trending signal: {signal['keyword']} (velocity: {signal.get('velocity_score', 0):.0f}/100, source: {signal.get('platform', 'unknown')})",
                    source_data={"type": "trend_signal", "signal": signal},
                    expires_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                ))
        
        # 4. Default fallback niches if nothing else
        if not directives:
            default_niches = [
                "Stainless Steel Insulated Water Bottle",
                "Wireless Earbuds Noise Cancellation",
                "Portable Blender USB Rechargeable",
                "Electric Lunch Box Food Warmer",
                "Magnetic Wireless Car Charger",
            ]
            for i, niche in enumerate(default_niches):
                directives.append(ResearchDirective(
                    category=niche,
                    region="India",
                    priority_score=50 - i * 3,
                    rationale=f"Default bootstrap niche #{i+1}",
                    source_data={"type": "bootstrap"},
                    expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                ))
        
        # Sort by priority and limit
        directives.sort(key=lambda d: d.priority_score, reverse=True)
        return directives[:max_directives]
    
    def _extract_category_from_keyword(self, keyword: str) -> Optional[str]:
        """Map keyword to a product category."""
        category_keywords = {
            "water bottle": "Stainless Steel Insulated Water Bottle",
            "earbuds": "Wireless Earbuds Noise Cancellation",
            "blender": "Portable Blender USB Rechargeable",
            "lunch box": "Electric Lunch Box Food Warmer",
            "car charger": "Magnetic Wireless Car Charger",
            "air fryer": "Silicone Air Fryer Liners",
            "vacuum": "Cordless Handheld Vacuum Cleaner",
            "desk lamp": "Smart LED Desk Lamp Wireless Charging",
            "neck fan": "Portable Neck Fan USB Rechargeable",
            "food storage": "Collapsible Silicone Food Storage",
            "gadget": "Portable Rechargeable Gadgets",
            "kitchen": "Kitchen Gadgets Under 1000",
            "home organizer": "Home Organization",
            "car accessory": "Car Accessories",
            "fitness": "Fitness Equipment",
            "beauty": "Beauty Tools",
            "pet": "Pet Products",
            "office": "Office Accessories",
            "travel": "Travel Essentials",
            "smart home": "Smart Home Devices",
        }
        
        for kw, cat in category_keywords.items():
            if kw in keyword:
                return cat
        return None
    
    def write_directives(self, directives: List[ResearchDirective]) -> int:
        """Write directives to database, deactivating old ones."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        # Deactivate expired/old directives
        cur.execute("""
            UPDATE research_directives 
            SET status = 'EXPIRED' 
            WHERE status = 'ACTIVE' 
            AND (expires_at < datetime('now') OR created_at < datetime('now', '-7 days'))
        """)
        
        written = 0
        for d in directives:
            try:
                cur.execute('''
                    INSERT INTO research_directives 
                    (category, region, priority_score, rationale, source_data, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    d.category, d.region, d.priority_score, d.rationale,
                    json.dumps(d.source_data), d.expires_at
                ))
                written += 1
            except Exception as e:
                logger.warning(f"Failed to write directive for {d.category}: {e}")
        
        conn.commit()
        logger.info(f"Wrote {written} research directives")
        return written
    
    def run_weekly_planning(self) -> Dict[str, Any]:
        """Main entry point: run full weekly planning cycle."""
        logger.info("=" * 50)
        logger.info("STRATEGY PLANNER: Starting weekly planning cycle")
        logger.info("=" * 50)
        
        directives = self.generate_directives()
        written = self.write_directives(directives)
        
        summary = {
            "directives_generated": len(directives),
            "directives_written": written,
            "top_priorities": [
                {"category": d.category, "region": d.region, "priority": d.priority_score, "rationale": d.rationale[:100]}
                for d in directives[:5]
            ],
        }
        
        logger.info(f"Planning complete: {written} directives written")
        for d in directives[:3]:
            logger.info(f"  TOP: {d.category} ({d.region}) - Priority: {d.priority_score:.1f} - {d.rationale[:80]}")
        
        return summary


async def run_strategy_planner() -> Dict[str, Any]:
    """Async entry point for orchestrator."""
    planner = StrategyPlanner()
    return planner.run_weekly_planning()


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_strategy_planner())
    print(json.dumps(result, indent=2, default=str))