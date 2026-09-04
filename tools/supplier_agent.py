"""
tools/supplier_agent.py — Supplier Discovery & Verification Agent for APRS V7.

Discovers and verifies suppliers on IndiaMART, Alibaba, and other platforms.
Includes GST verification via mastergst.com API.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import sys

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from core.database import (
    get_connection, add_supplier_profile, get_supplier_profiles_for_product,
    update_supplier_profile, add_outreach_draft,
)
from tools.web_agent import WebAgent
from tools.gst_verifier import verify_gst
from core.supplier_models import SupplierProfile, SupplierSearchResult, SupplierVerificationResult

logger = logging.getLogger("aprs.supplier_agent")


@dataclass
class SupplierAgentResult:
    """Result of supplier agent batch run."""
    suppliers_found: int = 0
    suppliers_verified: int = 0
    sources_scanned: int = 0
    outreach_drafts_created: int = 0


class SupplierAgent:
    """
    Supplier Discovery & Verification Agent.

    Capabilities:
    1. Discover suppliers on IndiaMART, Alibaba, ExportersIndia, TradeIndia
    2. Verify GST numbers via mastergst.com API
    3. Score supplier profiles (verification badge, GST validity, responsiveness)
    4. Generate outreach drafts for human approval
    5. Track conversation history
    """

    def __init__(self):
        self.web_agent = WebAgent()
        self.llm_router = None  # Lazy init
        self._session = None

    async def __aenter__(self):
        await self._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()

    async def _init_session(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10),
        )

    async def _close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_llm_router(self):
        if self.llm_router is None:
            from core.llm_router import LLMRouter
            self.llm_router = LLMRouter()
        return self.llm_router

    async def run_batch(self, limit: int = 10) -> Dict[str, Any]:
        """
        Run supplier discovery for products that passed Gate 4.
        
        Returns summary of suppliers found and verified.
        """
        logger.info("Starting supplier discovery batch")

        # Get products that passed Gate 4 (ready for supplier outreach)
        products = await self._get_products_ready_for_sourcing(limit=limit)

        results = {
            "suppliers_found": 0,
            "suppliers_verified": 0,
            "sources_scanned": 0,
            "outreach_drafts_created": 0,
        }

        for product in products:
            try:
                result = await self.process_product(product)
                results["suppliers_found"] += result.get("suppliers_found", 0)
                results["suppliers_verified"] += result.get("suppliers_verified", 0)
                results["sources_scanned"] += result.get("sources_scanned", 0)
                results["outreach_drafts_created"] += result.get("outreach_drafts_created", 0)
            except Exception as e:
                logger.error(f"Supplier processing failed for {product.get('product_id')}: {e}")

        logger.info(f"Supplier batch complete: {results}")
        return results

    async def _get_products_ready_for_sourcing(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get products that passed Gate 4 (Scoring) and are ready for supplier outreach.
        These are products with status PROCEED or SOURCING_NEGOTIATION.
        """
        from core.database import get_connection
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Get products that passed Gate 4 (Scoring gate) - gate 4 = SOURCING_QUOTE in old terms
        # In new 5-gate: Gate 4 = Scoring, Gate 5 = NIM Arbiter
        # Products ready for sourcing are those that passed Gate 4
        cur.execute('''
            SELECT p.* FROM master_products p
            JOIN product_gate_progress g ON p.product_id = g.product_id
            WHERE g.gate_number = 4 
            AND g.status IN ('PASS', 'OVERRIDDEN')
            AND p.is_deleted = 0
            AND p.status NOT IN ('LIVE', 'SHIPPED')
            ORDER BY p.overall_score DESC
            LIMIT ?
        ''', (limit,))
        
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        
        logger.info(f"Found {len(rows)} products ready for sourcing")
        return rows

    async def process_product(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single product: discover suppliers, verify them, create outreach drafts.
        """
        product_id = product.get("product_id")
        product_name = product.get("name", "")
        category = product.get("category", "General")

        logger.info(f"Processing suppliers for product: {product_name}")

        # 1. Discover suppliers on multiple platforms
        suppliers = await self.discover_suppliers(product)
        
        if not suppliers:
            logger.warning(f"No suppliers found for product {product_id}")
            return {"suppliers_found": 0, "suppliers_verified": 0, "sources_scanned": 0, "outreach_drafts_created": 0}

        # 2. Verify each supplier (GST, profile completeness)
        verified_suppliers = []
        for supplier in suppliers:
            verification = await self.verify_supplier(supplier)
            if verification.gst_valid:
                verified_suppliers.append(supplier)
        
        # 3. Create outreach drafts for verified suppliers
        outreach_created = 0
        for supplier in verified_suppliers[:5]:  # Limit to top 5
            draft = await self.create_outreach_draft(supplier, product)
            if draft:
                outreach_created += 1

        return {
            "suppliers_found": len(suppliers),
            "suppliers_verified": len(verified_suppliers),
            "sources_scanned": len(suppliers),
            "outreach_drafts_created": outreach_created,
        }

    async def discover_suppliers(self, product: Dict[str, Any]) -> List[SupplierSearchResult]:
        """Discover suppliers on multiple platforms."""
        product_name = product.get("name", "")
        category = product.get("category", "General")
        product_id = product.get("product_id")

        all_suppliers = []

        # Search on IndiaMART (primary for India)
        indiamart_suppliers = await self._search_indiamart(product)
        all_suppliers.extend(indiamart_suppliers)

        # Search on Alibaba (international)
        alibaba_suppliers = await self._search_alibaba(product)
        all_suppliers.extend(alibaba_suppliers)

        # Search on ExportersIndia
        exporters_suppliers = await self._search_exporters_india(product)
        all_suppliers.extend(exporters_suppliers)

        # Search on TradeIndia
        tradeindia_suppliers = await self._search_tradeindia(product)
        all_suppliers.extend(tradeindia_suppliers)

        # Deduplicate by company name + platform
        unique_suppliers = self._deduplicate_suppliers(all_suppliers)

        logger.info(f"Found {len(unique_suppliers)} unique suppliers for product {product_id}")
        return unique_suppliers

    async def _search_indiamart(self, product: Dict[str, Any]) -> List[SupplierSearchResult]:
        """Search suppliers on IndiaMART."""
        product_name = product.get("name", "")
        query = product.get("name", "").replace(" ", "+")
        url = f"https://dir.indiamart.com/search.mp?ss={query}"

        agent = WebAgent()
        suppliers = await agent.search_products(
            query=product.get("name", ""),
            site="indiamart",
            max_results=10,
        )

        results = []
        for s in suppliers:
            results.append(SupplierSearchResult(
                company_name=s.get("company_name", s.get("title", "")),
                platform="indiamart",
                profile_url=s.get("profile_url", s.get("url", "")),
                contact_phone=s.get("contact_phone"),
                contact_email=s.get("contact_email"),
                gst_number=s.get("gst_number"),
                moq_estimate=s.get("moq_estimate"),
                verification_badge=s.get("verification_badge", False),
                product_categories=s.get("product_categories", ""),
                location=s.get("location"),
            ))
        return results

    async def _search_alibaba(self, product: Dict[str, Any]) -> List[SupplierSearchResult]:
        """Search suppliers on Alibaba."""
        product_name = product.get("name", "")
        query = product.get("name", "").replace(" ", "+")
        url = f"https://www.alibaba.com/trade/search?SearchText={query}"

        agent = WebAgent()
        suppliers = await agent.search_products(
            query=product.get("name", ""),
            site="alibaba",
            max_results=8,
        )

        results = []
        for s in suppliers:
            results.append(SupplierSearchResult(
                company_name=s.get("company_name", s.get("title", "")),
                platform="alibaba",
                profile_url=s.get("profile_url", s.get("url", "")),
                contact_phone=s.get("contact_phone"),
                contact_email=s.get("contact_email"),
                gst_number=s.get("gst_number"),
                moq_estimate=s.get("moq_estimate"),
                verification_badge=s.get("verification_badge", False),
                product_categories=s.get("product_categories", ""),
                location=s.get("location"),
            ))
        return results

    async def _search_exporters_india(self, product: Dict[str, Any]) -> List[SupplierSearchResult]:
        """Search suppliers on ExportersIndia."""
        query = product.get("name", "").replace(" ", "+")
        url = f"https://www.exportersindia.com/search/?search={query}"

        agent = WebAgent()
        suppliers = await agent.search_products(
            query=product.get("name", ""),
            site="exportersindia",
            max_results=5,
        )

        results = []
        for s in suppliers:
            results.append(SupplierSearchResult(
                company_name=s.get("company_name", s.get("title", "")),
                platform="exportersindia",
                profile_url=s.get("profile_url", s.get("url", "")),
                contact_phone=s.get("contact_phone"),
                contact_email=s.get("contact_email"),
                gst_number=s.get("gst_number"),
                moq_estimate=s.get("moq_estimate"),
                verification_badge=s.get("verification_badge", False),
                product_categories=s.get("product_categories", ""),
                location=s.get("location"),
            ))
        return results

    async def _search_tradeindia(self, product: Dict[str, Any]) -> List[SupplierSearchResult]:
        """Search suppliers on TradeIndia."""
        query = product.get("name", "").replace(" ", "+")
        url = f"https://www.tradeindia.com/search.html?search_str={query}"

        agent = WebAgent()
        suppliers = await agent.search_products(
            query=product.get("name", ""),
            site="tradeindia",
            max_results=5,
        )

        results = []
        for s in suppliers:
            results.append(SupplierSearchResult(
                company_name=s.get("company_name", s.get("title", "")),
                platform="tradeindia",
                profile_url=s.get("profile_url", s.get("url", "")),
                contact_phone=s.get("contact_phone"),
                contact_email=s.get("contact_email"),
                gst_number=s.get("gst_number"),
                moq_estimate=s.get("moq_estimate"),
                verification_badge=s.get("verification_badge", False),
                product_categories=s.get("product_categories", ""),
                location=s.get("location"),
            ))
        return results

    def _deduplicate_suppliers(self, suppliers: List[SupplierSearchResult]) -> List[SupplierSearchResult]:
        """Deduplicate suppliers by company name + platform."""
        seen = set()
        unique = []
        for s in suppliers:
            key = (s.company_name.lower().strip(), s.platform)
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    async def verify_supplier(self, supplier: SupplierSearchResult) -> SupplierVerificationResult:
        """
        Verify a supplier's GST number and profile completeness.
        """
        verification = SupplierVerificationResult(
            supplier_id=supplier.company_name,
            gst_valid=False,
            gst_check_date=datetime.utcnow().isoformat(),
        )

        # 1. GST Verification via mastergst.com
        if supplier.gst_number:
            gst_result = await verify_gst(supplier.gst_number)
            verification.gst_valid = gst_result.gst_valid
            verification.gst_check_date = gst_result.gst_check_date
            verification.gst_details = gst_result.gst_details
            verification.company_name_match = gst_result.company_name_match
            verification.address_match = gst_result.address_match
            verification.verification_score = gst_result.verification_score
            verification.check_duration_ms = gst_result.check_duration_ms
            verification.error = gst_result.error

        # 2. Profile completeness check
        profile_score = 0
        if supplier.company_name: profile_score += 20
        if supplier.profile_url: profile_score += 10
        if supplier.contact_phone: profile_score += 15
        if supplier.contact_email: profile_score += 15
        if supplier.gst_number: profile_score += 20
        if supplier.verification_badge: profile_score += 10
        if supplier.moq_estimate: profile_score += 10
        if supplier.product_categories: profile_score += 10

        verification.verification_score = max(verification.verification_score, profile_score)

        # 3. Determine overall validity
        verification.gst_valid = verification.gst_valid and verification.verification_score >= 60

        return verification

    async def create_outreach_draft(self, supplier: SupplierSearchResult, product: Dict[str, Any]) -> Optional[int]:
        """Create an outreach draft for a verified supplier."""
        from core.outreach_engine import OutreachEngine, create_initial_outreach
        from core.supplier_models import OutreachChannel

        engine = OutreachEngine()
        
        # Determine best channel
        channel = "email"
        if supplier.contact_phone and supplier.platform == "indiamart":
            channel = "whatsapp"
        elif supplier.platform in ["indiamart", "tradeindia"]:
            channel = "indiamart_chat"

        custom_vars = {
            "product_spec": product.get("name", ""),
            "target_moq": str(supplier.moq_estimate or "500"),
            "target_price": "competitive",
            "v2_improvements": product.get("upgrade_v2", "quality improvements"),
            "company_name": supplier.company_name,
            "platform": supplier.platform,
        }

        draft = await create_initial_outreach(
            supplier_id=supplier.company_name,  # Using company name as ID for now
            product_id=product.get("product_id", ""),
            template_id="initial_contact_v1",
            channel=channel,
            custom_vars=custom_vars,
        )

        return draft.draft_id if draft else None


async def run_supplier_batch(limit: int = 10) -> Dict[str, Any]:
    """Run supplier discovery batch for products ready for sourcing."""
    async with SupplierAgent() as agent:
        return await agent.run_batch(limit=limit)


if __name__ == "__main__":
    async def test():
        result = await run_supplier_batch(limit=5)
        print(f"Supplier batch result: {result}")

    asyncio.run(test())