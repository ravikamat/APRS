"""
tests/test_validation_schemas.py — Unit tests for Pydantic validation schemas.
Tests RawProduct, CanonicalProduct, and ValidationPipeline.
"""
import pytest
from pydantic import ValidationError

from core.validation import RawProduct, CanonicalProduct, ProductMatcher, ValidationPipeline


class TestRawProduct:
    """Tests for RawProduct schema."""

    def test_valid_raw_product_amazon(self):
        """Valid Amazon product should pass validation."""
        product = RawProduct(
            marketplace="amazon",
            product_id="B09XYZ123",
            title="Stainless Steel Insulated Water Bottle 1 Litre",
            price=1299.0,
            rating=4.5,
            review_count=250,
            bsr=15000,
            url="https://www.amazon.in/dp/B09XYZ123",
            image_url="https://example.com/image.jpg",
        )
        assert product.marketplace == "amazon"
        assert product.price == 1299.0
        assert product.rating == 4.5

    def test_valid_raw_product_flipkart(self):
        """Valid Flipkart product should pass validation."""
        product = RawProduct(
            marketplace="flipkart",
            product_id="FKT12345",
            title="Wireless Earbuds with Noise Cancellation",
            price=2499.0,
            rating=4.2,
            review_count=180,
            url="https://www.flipkart.com/p/FKT12345",
        )
        assert product.marketplace == "flipkart"
        assert product.bsr is None

    def test_valid_raw_product_meesho(self):
        """Valid Meesho product should pass validation."""
        product = RawProduct(
            marketplace="meesho",
            product_id="MSH789",
            title="Cotton Kurta Set for Women",
            price=799.0,
            rating=4.0,
            review_count=95,
            url="https://www.meesho.com/p/MSH789",
        )
        assert product.marketplace == "meesho"

    def test_invalid_marketplace(self):
        """Invalid marketplace should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RawProduct(
                marketplace="ebay",
                product_id="123",
                title="Test Product",
                price=100.0,
                rating=4.0,
                review_count=10,
                url="https://example.com",
            )
        assert "marketplace" in str(exc_info.value).lower()

    def test_price_must_be_positive(self):
        """Price must be > 0."""
        with pytest.raises(ValidationError) as exc_info:
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Test Product",
                price=0.0,
                rating=4.0,
                review_count=10,
                url="https://example.com",
            )
        assert "price" in str(exc_info.value).lower()

    def test_price_upper_bound(self):
        """Price must be <= 500000."""
        with pytest.raises(ValidationError) as exc_info:
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Test Product",
                price=600000.0,
                rating=4.0,
                review_count=10,
                url="https://example.com",
            )
        assert "price" in str(exc_info.value).lower()

    def test_rating_bounds(self):
        """Rating must be between 1.0 and 5.0."""
        with pytest.raises(ValidationError):
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Test Product",
                price=100.0,
                rating=0.5,
                review_count=10,
                url="https://example.com",
            )
        with pytest.raises(ValidationError):
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Test Product",
                price=100.0,
                rating=5.5,
                review_count=10,
                url="https://example.com",
            )

    def test_review_count_non_negative(self):
        """Review count must be >= 0."""
        with pytest.raises(ValidationError):
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Test Product",
                price=100.0,
                rating=4.0,
                review_count=-1,
                url="https://example.com",
            )

    def test_title_min_length(self):
        """Title must be at least 5 characters."""
        with pytest.raises(ValidationError):
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Test",
                price=100.0,
                rating=4.0,
                review_count=10,
                url="https://example.com",
            )

    def test_title_max_length(self):
        """Title must be at most 300 characters."""
        with pytest.raises(ValidationError):
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="A" * 301,
                price=100.0,
                rating=4.0,
                review_count=10,
                url="https://example.com",
            )

    def test_placeholder_title_rejected(self):
        """Generic placeholder titles < 20 chars should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Test Placeholder",
                price=100.0,
                rating=4.0,
                review_count=10,
                url="https://example.com",
            )
        assert "placeholder" in str(exc_info.value).lower()

    def test_url_format(self):
        """URL must be valid http/https."""
        with pytest.raises(ValidationError):
            RawProduct(
                marketplace="amazon",
                product_id="B09XYZ123",
                title="Valid Product Title Here",
                price=100.0,
                rating=4.0,
                review_count=10,
                url="not-a-url",
            )

    def test_optional_fields(self):
        """Optional fields should work correctly."""
        product = RawProduct(
            marketplace="amazon",
            product_id="B09XYZ123",
            title="Valid Product Title Here",
            price=100.0,
            rating=4.0,
            review_count=10,
            url="https://example.com",
        )
        assert product.bsr is None
        assert product.image_url is None


class TestCanonicalProduct:
    """Tests for CanonicalProduct schema."""

    def test_valid_canonical_product(self):
        """Valid canonical product should pass."""
        product = CanonicalProduct(
            canonical_title="Stainless Steel Insulated Water Bottle",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_asin="B09XYZ123",
            flipkart_id="FKT12345",
            meesho_id="MSH789",
            rating=4.4,
            review_count=500,
            amazon_bsr=12000,
            factory_fob_inr=350.0,
            packaging_cost_inr=15.0,
            freight_per_unit_inr=35.0,
            mold_cost_inr=5000.0,
            mold_amort_units=5000,
            current_gate=1,
            gate_status="PENDING",
            final_score=82.5,
        )
        assert product.canonical_title == "Stainless Steel Insulated Water Bottle"
        assert product.retail_price_inr == 1299.0

    def test_minimal_canonical_product(self):
        """Minimal canonical product with defaults."""
        product = CanonicalProduct(
            canonical_title="Minimal Product",
            retail_price_inr=999.0,
            rating=4.0,
            review_count=50,
        )
        assert product.packaging_cost_inr == 15.0
        assert product.freight_per_unit_inr == 35.0
        assert product.mold_cost_inr == 0.0
        assert product.mold_amort_units == 5000
        assert product.current_gate == 1
        assert product.gate_status == "PENDING"
        assert product.final_score is None


class TestProductMatcher:
    """Tests for ProductMatcher fuzzy deduplication."""

    def test_normalize_title(self):
        """Title normalization should strip stop words and punctuation."""
        matcher = ProductMatcher()
        normalized = matcher.normalize_title("Best Premium Pro Portable Water Bottle 2024")
        assert "best" not in normalized
        assert "premium" not in normalized
        assert "pro" not in normalized
        assert "portable" not in normalized
        assert "2024" not in normalized
        assert "water bottle" in normalized

    def test_similarity_identical(self):
        """Identical titles should have similarity 1.0."""
        matcher = ProductMatcher()
        sim = matcher.similarity("water bottle", "water bottle")
        assert sim == 1.0

    def test_similarity_different(self):
        """Different titles should have lower similarity."""
        matcher = ProductMatcher()
        sim = matcher.similarity("water bottle", "coffee mug")
        assert sim < 0.5

    def test_find_canonical_single_product(self):
        """Single product should become its own canonical."""
        matcher = ProductMatcher()
        products = [
            RawProduct(
                marketplace="amazon",
                product_id="B001",
                title="Stainless Steel Water Bottle 1L",
                price=1299.0,
                rating=4.5,
                review_count=200,
                url="https://amazon.in/dp/B001",
            )
        ]
        canonicals = matcher.find_canonical(products)
        assert len(canonicals) == 1
        assert canonicals[0].canonical_title == "Stainless Steel Water Bottle 1L"

    def test_find_canonical_duplicate_detection(self):
        """Similar products across marketplaces should be deduplicated."""
        matcher = ProductMatcher()
        products = [
            RawProduct(
                marketplace="amazon",
                product_id="B001",
                title="Stainless Steel Insulated Water Bottle 1 Litre",
                price=1299.0,
                rating=4.5,
                review_count=200,
                bsr=15000,
                url="https://amazon.in/dp/B001",
            ),
            RawProduct(
                marketplace="flipkart",
                product_id="FKT001",
                title="Stainless Steel Insulated Water Bottle 1L",
                price=1249.0,
                rating=4.4,
                review_count=180,
                url="https://flipkart.com/p/FKT001",
            ),
        ]
        canonicals = matcher.find_canonical(products)
        assert len(canonicals) == 1
        assert canonicals[0].amazon_asin == "B001"
        assert canonicals[0].flipkart_id == "FKT001"
        assert abs(canonicals[0].retail_price_inr - 1274.0) < 1.0

    def test_find_canonical_distinct_products(self):
        """Distinct products should remain separate."""
        matcher = ProductMatcher()
        products = [
            RawProduct(
                marketplace="amazon",
                product_id="B001",
                title="Stainless Steel Water Bottle",
                price=1299.0,
                rating=4.5,
                review_count=200,
                url="https://amazon.in/dp/B001",
            ),
            RawProduct(
                marketplace="amazon",
                product_id="B002",
                title="Ceramic Coffee Mug Set",
                price=599.0,
                rating=4.2,
                review_count=150,
                url="https://amazon.in/dp/B002",
            ),
        ]
        canonicals = matcher.find_canonical(products)
        assert len(canonicals) == 2


class TestValidationPipeline:
    """Tests for ValidationPipeline batch validation."""

    def test_validate_batch_all_valid(self):
        """All valid products should pass."""
        pipeline = ValidationPipeline()
        raw_products = [
            {
                "marketplace": "amazon",
                "product_id": "B001",
                "title": "Valid Product Title Here",
                "price": 1000.0,
                "rating": 4.5,
                "review_count": 100,
                "url": "https://amazon.in/dp/B001",
            },
            {
                "marketplace": "flipkart",
                "product_id": "FKT001",
                "title": "Another Valid Product Title",
                "price": 1500.0,
                "rating": 4.2,
                "review_count": 80,
                "url": "https://flipkart.com/p/FKT001",
            },
        ]
        valid, errors = pipeline.validate_batch(raw_products)
        assert len(valid) == 2
        assert len(errors) == 0

    def test_validate_batch_mixed(self):
        """Mixed valid/invalid should separate correctly."""
        pipeline = ValidationPipeline()
        raw_products = [
            {
                "marketplace": "amazon",
                "product_id": "B001",
                "title": "Valid Product Title Here",
                "price": 1000.0,
                "rating": 4.5,
                "review_count": 100,
                "url": "https://amazon.in/dp/B001",
            },
            {
                "marketplace": "invalid_marketplace",
                "product_id": "B002",
                "title": "Invalid Product",
                "price": 1000.0,
                "rating": 4.5,
                "review_count": 100,
                "url": "https://example.com",
            },
        ]
        valid, errors = pipeline.validate_batch(raw_products)
        assert len(valid) == 1
        assert len(errors) == 1
        assert errors[0]["error"] is not None

    def test_deduplicate(self):
        """Deduplication should use ProductMatcher."""
        pipeline = ValidationPipeline()
        products = [
            RawProduct(
                marketplace="amazon",
                product_id="B001",
                title="Stainless Steel Water Bottle",
                price=1299.0,
                rating=4.5,
                review_count=200,
                url="https://amazon.in/dp/B001",
            ),
            RawProduct(
                marketplace="flipkart",
                product_id="FKT001",
                title="Stainless Steel Water Bottle 1L",
                price=1249.0,
                rating=4.4,
                review_count=180,
                url="https://flipkart.com/p/FKT001",
            ),
        ]
        canonicals = pipeline.deduplicate(products)
        assert len(canonicals) == 1


class TestScoringEngine:
    """Tests for deterministic scoring engine."""

    def test_score_proceed(self):
        """High-scoring product should PROCEED."""
        from core.scoring_engine import ScoringEngine
        engine = ScoringEngine()
        result = engine.score(
            bsr=10000,
            rating=4.5,
            review_count=200,
            net_margin_pct=30.0,
            has_defects=True,
            competitor_count=3,
        )
        assert result.verdict == "PROCEED"
        assert result.total >= 75

    def test_score_marginal(self):
        """Medium-scoring product should be MARGINAL."""
        from core.scoring_engine import ScoringEngine
        engine = ScoringEngine()
        result = engine.score(
            bsr=25000,
            rating=4.0,
            review_count=80,
            net_margin_pct=22.0,
            has_defects=True,
            competitor_count=8,
        )
        assert result.verdict == "MARGINAL"
        assert 60 <= result.total < 75

    def test_score_reject(self):
        """Low-scoring product should REJECT."""
        from core.scoring_engine import ScoringEngine
        engine = ScoringEngine()
        result = engine.score(
            bsr=50000,
            rating=3.5,
            review_count=30,
            net_margin_pct=15.0,
            has_defects=False,
            competitor_count=15,
        )
        assert result.verdict == "REJECT"
        assert result.total < 60

    def test_score_no_bsr(self):
        """Missing BSR should get default market signal score."""
        from core.scoring_engine import ScoringEngine
        engine = ScoringEngine()
        result = engine.score(
            bsr=None,
            rating=4.5,
            review_count=200,
            net_margin_pct=30.0,
            has_defects=True,
            competitor_count=3,
        )
        assert result.market_signal == 20.0

    def test_score_breakdown_components(self):
        """Each score component should be calculated correctly."""
        from core.scoring_engine import ScoringEngine
        engine = ScoringEngine()
        result = engine.score(
            bsr=5000,
            rating=4.5,
            review_count=200,
            net_margin_pct=30.0,
            has_defects=True,
            competitor_count=3,
        )
        assert result.market_signal == 22.5  # 25 - (5000/2000)
        assert result.review_quality == 20.0  # rating >= 4.2 & reviews >= 100
        assert result.margin_safety == 40.0  # >= 30%
        assert result.defect_fixability == 10.0  # has defects
        assert result.competition_density == 5.0  # <= 5 competitors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])