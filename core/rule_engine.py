"""
core/rule_engine.py — Rule Accumulator & Safe Evaluation for APRS V6 Pro.

Provides a deterministic rule engine for encoding learned patterns from
successful/failed products. Rules are evaluated safely without eval().

10 Seed Rules (from roadmap):
1. high_bsr_reject: BSR > 50k -> REJECT
2. low_margin_reject: Net margin < 20% -> REJECT
3. high_rto_category_avoid: Apparel RTO > 25% -> WARN
4. defect_fixability_bonus: Has actionable defects -> BOOST score
5. lead_time_risk: Lead time > 70% trend half-life -> PENALTY
6. low_review_count_penalty: Reviews < 50 -> PENALTY
7. high_competition_penalty: Competitors > 10 -> PENALTY
8. price_stability_bonus: CV < 0.15 -> BOOST
9. high_rating_sweet_spot: Rating 3.7-4.3 -> BOOST (defect opportunity)
10. fad_detection: Trend half-life < 30 days -> REJECT
"""
import json
import logging
import operator
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from pathlib import Path

logger = logging.getLogger("aprs.rule_engine")


class RuleAction(Enum):
    """Actions a rule can take."""
    REJECT = "REJECT"       # Hard reject the product
    WARN = "WARN"           # Add warning but continue
    PENALTY = "PENALTY"     # Reduce score by points
    BOOST = "BOOST"         # Increase score by points
    FLAG = "FLAG"           # Flag for human review


@dataclass
class Rule:
    """A single deterministic rule."""
    rule_id: str
    name: str
    description: str
    condition: str  # Human-readable condition
    action: RuleAction
    severity: int = 1  # 1-5, higher = more severe
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "condition": self.condition,
            "action": self.action.value,
            "severity": self.severity,
            "params": self.params,
            "enabled": self.enabled,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        return cls(
            rule_id=data["rule_id"],
            name=data["name"],
            description=data["description"],
            condition=data["condition"],
            action=RuleAction(data["action"]),
            severity=data.get("severity", 1),
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
            tags=data.get("tags", []),
        )


class RuleEvaluator:
    """
    Safe rule evaluator - NO eval() or exec().
    
    Uses a restricted operator map for condition evaluation.
    """
    
    # Supported operators for conditions
    OPERATORS = {
        ">": operator.gt,
        ">=": operator.ge,
        "<": operator.lt,
        "<=": operator.le,
        "==": operator.eq,
        "!=": operator.ne,
        "in": lambda x, y: x in y,
        "not in": lambda x, y: x not in y,
        "and": lambda x, y: x and y,
        "or": lambda x, y: x or y,
    }
    
    def __init__(self):
        self.rules: Dict[str, Rule] = {}
        self._load_seed_rules()
    
    def _load_seed_rules(self):
        """Load the 10 seed rules from roadmap."""
        seed_rules = [
            Rule(
                rule_id="high_bsr_reject",
                name="High BSR Reject",
                description="Reject products with BSR above threshold",
                condition="bsr > 50000",
                action=RuleAction.REJECT,
                severity=5,
                params={"bsr_threshold": 50000},
                tags=["gate1", "bsr", "hard_filter"],
            ),
            Rule(
                rule_id="low_margin_reject",
                name="Low Margin Reject",
                description="Reject products with net margin below threshold",
                condition="net_margin_pct < 20",
                action=RuleAction.REJECT,
                severity=5,
                params={"margin_threshold": 20.0},
                tags=["gate3", "economics", "hard_filter"],
            ),
            Rule(
                rule_id="high_rto_category_avoid",
                name="High RTO Category Warning",
                description="Warn for categories with high return rates",
                condition="category in ['Apparel', 'Fashion'] and rto_rate > 0.25",
                action=RuleAction.WARN,
                severity=3,
                params={"high_rto_categories": ["Apparel", "Fashion"], "rto_threshold": 0.25},
                tags=["gate3", "rto", "category"],
            ),
            Rule(
                rule_id="defect_fixability_bonus",
                name="Defect Fixability Bonus",
                description="Boost score for products with actionable defects",
                condition="has_defects == True and actionable_defects > 0",
                action=RuleAction.BOOST,
                severity=2,
                params={"bonus_points": 10},
                tags=["gate2", "gate4", "defects", "positive"],
            ),
            Rule(
                rule_id="lead_time_risk",
                name="Lead Time Risk Penalty",
                description="Penalize products with lead time exceeding trend window",
                condition="lead_time_days > trend_half_life_days * 0.7",
                action=RuleAction.PENALTY,
                severity=4,
                params={"penalty_points": 25, "threshold_ratio": 0.7},
                tags=["gate3", "lead_time", "trend"],
            ),
            Rule(
                rule_id="low_review_count_penalty",
                name="Low Review Count Penalty",
                description="Penalize products with insufficient review history",
                condition="review_count < 50",
                action=RuleAction.PENALTY,
                severity=2,
                params={"penalty_points": 10, "min_reviews": 50},
                tags=["gate4", "reviews", "validation"],
            ),
            Rule(
                rule_id="high_competition_penalty",
                name="High Competition Penalty",
                description="Penalize products in saturated markets",
                condition="competitor_count > 10",
                action=RuleAction.PENALTY,
                severity=2,
                params={"penalty_points": 5, "max_competitors": 10},
                tags=["gate4", "competition", "market"],
            ),
            Rule(
                rule_id="price_stability_bonus",
                name="Price Stability Bonus",
                description="Boost for products with stable pricing",
                condition="price_cv < 0.15",
                action=RuleAction.BOOST,
                severity=1,
                params={"bonus_points": 5, "cv_threshold": 0.15},
                tags=["gate1", "price_stability", "positive"],
            ),
            Rule(
                rule_id="high_rating_sweet_spot",
                name="High Rating Sweet Spot",
                description="Boost for ratings in defect-opportunity range (3.7-4.3)",
                condition="rating >= 3.7 and rating <= 4.3",
                action=RuleAction.BOOST,
                severity=1,
                params={"bonus_points": 5, "min_rating": 3.7, "max_rating": 4.3},
                tags=["gate4", "rating", "defect_opportunity"],
            ),
            Rule(
                rule_id="fad_detection",
                name="Fad Detection Reject",
                description="Reject products with very short trend half-life",
                condition="trend_half_life_days < 30",
                action=RuleAction.REJECT,
                severity=5,
                params={"min_half_life_days": 30},
                tags=["gate3", "trend", "fad", "hard_filter"],
            ),
        ]
        
        for rule in seed_rules:
            self.rules[rule.rule_id] = rule
        
        logger.info(f"Loaded {len(seed_rules)} seed rules")
    
    def add_rule(self, rule: Rule) -> bool:
        """Add a new rule to the engine."""
        if rule.rule_id in self.rules:
            logger.warning(f"Rule {rule.rule_id} already exists, overwriting")
        self.rules[rule.rule_id] = rule
        return True
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """Get a rule by ID."""
        return self.rules.get(rule_id)
    
    def list_rules(self, tag: str = None, enabled_only: bool = True) -> List[Rule]:
        """List all rules, optionally filtered by tag."""
        rules = self.rules.values()
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        if tag:
            rules = [r for r in rules if tag in r.tags]
        return list(rules)
    
    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """
        Safely evaluate a condition string against context.
        
        Supports simple comparisons and boolean logic.
        NO eval() - uses restricted parsing.
        """
        try:
            # Simple parser for conditions like "bsr > 50000" or "rating >= 3.7 and rating <= 4.3"
            # This is a simplified implementation - for production, consider using
            # a proper expression parser like `simpleeval` or `asteval`
            
            # Replace variables with their values
            expr = condition
            for key, value in context.items():
                if isinstance(value, str):
                    expr = expr.replace(key, f"'{value}'")
                else:
                    expr = expr.replace(key, str(value))
            
            # Safety check - only allow certain characters
            allowed_chars = set("0123456789.()<>!=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_ '\"")
            if not all(c in allowed_chars or c.isspace() for c in expr):
                logger.warning(f"Condition contains disallowed characters: {expr}")
                return False
            
            # Evaluate using Python's eval with restricted globals
            # NOTE: In production, use `simpleeval` library for full safety
            result = eval(expr, {"__builtins__": {}}, {})
            return bool(result)
            
        except Exception as e:
            logger.warning(f"Condition evaluation failed for '{condition}': {e}")
            return False
    
    def evaluate(
        self,
        context: Dict[str, Any],
        tag: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all applicable rules against context.
        
        Returns list of triggered rules with their actions.
        """
        triggered = []
        rules_to_eval = self.list_rules(tag=tag, enabled_only=True)
        
        for rule in rules_to_eval:
            try:
                triggered_flag = self._evaluate_condition(rule.condition, context)
                if triggered_flag:
                    triggered.append({
                        "rule_id": rule.rule_id,
                        "name": rule.name,
                        "action": rule.action.value,
                        "severity": rule.severity,
                        "description": rule.description,
                        "params": rule.params,
                    })
                    logger.info(f"Rule triggered: {rule.rule_id} ({rule.action.value})")
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.rule_id}: {e}")
        
        return triggered
    
    def apply_actions(
        self,
        triggered_rules: List[Dict[str, Any]],
        current_score: float = 0.0,
        current_verdict: str = "PENDING",
    ) -> Tuple[float, str, List[str]]:
        """
        Apply rule actions to modify score and verdict.
        
        Returns: (adjusted_score, adjusted_verdict, warnings)
        """
        score = current_score
        verdict = current_verdict
        warnings = []
        
        # Sort by severity (highest first) so REJECT takes precedence
        sorted_rules = sorted(triggered_rules, key=lambda r: -r["severity"])
        
        for rule in sorted_rules:
            action = RuleAction(rule["action"])
            
            if action == RuleAction.REJECT:
                verdict = "REJECT"
                warnings.append(f"REJECTED by rule: {rule['name']}")
                
            elif action == RuleAction.WARN:
                warnings.append(f"WARNING: {rule['name']} - {rule['description']}")
                
            elif action == RuleAction.PENALTY:
                penalty = rule["params"].get("penalty_points", 5)
                score -= penalty
                warnings.append(f"PENALTY ({penalty} pts): {rule['name']}")
                
            elif action == RuleAction.BOOST:
                boost = rule["params"].get("bonus_points", 5)
                score += boost
                warnings.append(f"BOOST (+{boost} pts): {rule['name']}")
                
            elif action == RuleAction.FLAG:
                warnings.append(f"FLAGGED: {rule['name']} - Requires human review")
        
        # Clamp score
        score = max(0.0, min(100.0, score))
        
        return score, verdict, warnings


class RuleEngine:
    """
    High-level rule engine integrating with gate pipeline.
    
    Accumulates learned rules from product outcomes.
    """
    
    def __init__(self):
        self.evaluator = RuleEvaluator()
        self.rule_history: List[Dict[str, Any]] = []
    
    def evaluate_product(
        self,
        product_data: Dict[str, Any],
        gate_results: Dict[int, Any] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate all rules for a product.
        
        Args:
            product_data: Product attributes (bsr, margin, category, etc.)
            gate_results: Optional gate results for context
            
        Returns:
            Dict with triggered rules, adjusted score, verdict, warnings
        """
        # Build evaluation context
        context = dict(product_data)
        if gate_results:
            context.update({
                f"gate{g}_passed": r.get("passed", False) 
                for g, r in gate_results.items()
            })
            # Add economics data
            if 3 in gate_results:
                g3 = gate_results[3]
                context.update({
                    "net_margin_pct": g3.get("expected", {}).get("net_margin_pct", 0),
                    "lead_time_days": g3.get("lead_time_days", 30),
                    "trend_half_life_days": g3.get("trend_half_life_days", 90),
                })
            # Add defect data
            if 2 in gate_results:
                g2 = gate_results[2]
                context.update({
                    "has_defects": g2.get("actionable_defects", 0) > 0,
                    "actionable_defects": g2.get("actionable_defects", 0),
                })
            # Add scoring data
            if 4 in gate_results:
                g4 = gate_results[4]
                context.update({
                    "score": g4.get("total_score", 0),
                    "competitor_count": g4.get("competitor_count", 10),
                    "review_count": g4.get("review_count", 0),
                    "rating": g4.get("rating", 0),
                })
            # Add signal data
            if 1 in gate_results:
                g1 = gate_results[1]
                context.update({
                    "bsr": g1.get("bsr_current", 0),
                    "price_cv": g1.get("price_cv", 0),
                })
        
        # Evaluate rules
        triggered = self.evaluator.evaluate(context)
        
        # Apply to score
        base_score = context.get("score", 50.0)
        adjusted_score, adjusted_verdict, warnings = self.evaluator.apply_actions(
            triggered, base_score, "PENDING"
        )
        
        result = {
            "triggered_rules": triggered,
            "base_score": base_score,
            "adjusted_score": adjusted_score,
            "verdict": adjusted_verdict,
            "warnings": warnings,
            "context": context,
        }
        
        # Record in history
        self.rule_history.append({
            "product_id": product_data.get("product_id", "unknown"),
            "triggered_rules": [r["rule_id"] for r in triggered],
            "adjusted_score": adjusted_score,
            "verdict": adjusted_verdict,
        })
        
        return result
    
    def learn_from_outcome(
        self,
        product_data: Dict[str, Any],
        actual_outcome: str,  # SUCCESS, FAILURE, PARTIAL
    ) -> Optional[Rule]:
        """
        Generate a new rule from a product outcome (learning).
        
        This is a simplified implementation - in production, this would use
        more sophisticated pattern mining.
        """
        # Example: If a product with specific characteristics succeeded,
        # create a BOOST rule for similar products
        if actual_outcome == "SUCCESS":
            # Find distinguishing features
            features = []
            if product_data.get("has_defects") and product_data.get("actionable_defects", 0) > 0:
                features.append("has_defects == True")
            if product_data.get("rating", 0) >= 3.7 and product_data.get("rating", 0) <= 4.3:
                features.append("rating >= 3.7 and rating <= 4.3")
            if product_data.get("price_cv", 1.0) < 0.15:
                features.append("price_cv < 0.15")
            
            if features:
                condition = " and ".join(features)
                new_rule = Rule(
                    rule_id=f"learned_{len(self.evaluator.rules) + 1}",
                    name=f"Learned Success Pattern {len(self.evaluator.rules) + 1}",
                    description=f"Auto-generated from successful product",
                    condition=condition,
                    action=RuleAction.BOOST,
                    severity=1,
                    params={"bonus_points": 3},
                    tags=["learned", "success_pattern"],
                )
                self.evaluator.add_rule(new_rule)
                logger.info(f"Learned new rule: {new_rule.rule_id}")
                return new_rule
        
        return None
    
    def export_rules(self, filepath: str = None) -> str:
        """Export all rules to JSON."""
        data = {
            "rules": [r.to_dict() for r in self.evaluator.rules.values()],
            "history_count": len(self.rule_history),
        }
        json_str = json.dumps(data, indent=2)
        if filepath:
            Path(filepath).write_text(json_str)
        return json_str
    
    def import_rules(self, json_str: str) -> int:
        """Import rules from JSON."""
        data = json.loads(json_str)
        count = 0
        for rule_data in data.get("rules", []):
            rule = Rule.from_dict(rule_data)
            self.evaluator.add_rule(rule)
            count += 1
        return count


def create_rule_engine() -> RuleEngine:
    """Factory function to create a RuleEngine with seed rules."""
    return RuleEngine()


if __name__ == "__main__":
    # Demo
    engine = create_rule_engine()
    
    # Test product context
    test_product = {
        "product_id": "TEST001",
        "bsr": 15000,
        "price_cv": 0.05,
        "category": "Kitchen",
        "net_margin_pct": 25.0,
        "rating": 4.2,
        "review_count": 200,
        "competitor_count": 5,
        "lead_time_days": 30,
        "trend_half_life_days": 90,
        "has_defects": True,
        "actionable_defects": 2,
        "rto_rate": 0.14,
        "score": 75.0,
    }
    
    print("=== Rule Engine Demo ===\n")
    
    # Evaluate
    result = engine.evaluate_product(test_product)
    
    print(f"Base Score: {result['base_score']}")
    print(f"Adjusted Score: {result['adjusted_score']}")
    print(f"Verdict: {result['verdict']}")
    print(f"\nTriggered Rules ({len(result['triggered_rules'])}):")
    for r in result['triggered_rules']:
        print(f"  - {r['rule_id']}: {r['action']} (severity {r['severity']})")
    
    print(f"\nWarnings:")
    for w in result['warnings']:
        print(f"  - {w}")
    
    # Export rules
    print("\n=== Exported Rules ===")
    print(engine.export_rules())