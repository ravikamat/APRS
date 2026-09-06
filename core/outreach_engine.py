"""
core/outreach_engine.py — Outreach Engine for APRS V7.

Handles email/WhatsApp draft generation, human approval workflow,
and multi-channel sending (Email, WhatsApp, IndiaMART chat).
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import settings
from core.database import (
    get_connection, get_outreach_draft, update_outreach_draft,
    add_outreach_draft, get_pending_outreach_drafts,
    add_supplier_conversation, get_supplier_conversations,
)
from core.supplier_models import (
    OutreachDraft, OutreachChannel, OutreachStatus, OutreachTemplate,
    get_outreach_template,
)
from core.llm_router import LLMRouter, LLMTaskType

logger = logging.getLogger("aprs.outreach_engine")


@dataclass
class SendResult:
    """Result of sending an outreach message."""
    success: bool
    channel: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    sent_at: Optional[datetime] = None


class OutreachEngine:
    """
    Outreach Engine for supplier communication.
    
    Features:
    - Template-based draft generation using NIM 550B
    - Human approval workflow (DRAFT → APPROVED → SENT)
    - Multi-channel: Email (SMTP), WhatsApp (evolution-go), IndiaMART chat
    - Conversation threading and history
    - Automatic follow-up scheduling
    """
    
    def __init__(self, llm_router: Optional[LLMRouter] = None):
        self.llm_router = llm_router or LLMRouter()
        self._smtp_server: Optional[smtplib.SMTP] = None
    
    async def generate_draft(
        self,
        supplier_id: int,
        product_id: str,
        template_id: str = "initial_contact_v1",
        channel: str = "email",
        custom_vars: Optional[Dict[str, str]] = None,
    ) -> OutreachDraft:
        """
        Generate outreach draft using template + NIM 550B personalization.
        
        Args:
            supplier_id: Target supplier ID
            product_id: Product being sourced
            template_id: Template to use
            channel: Communication channel
            custom_vars: Additional template variables
            
        Returns:
            Created OutreachDraft (status=DRAFT)
        """
        template = get_outreach_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")
        
        # Get supplier details for personalization
        supplier = await self._get_supplier(supplier_id)
        product = await self._get_product(product_id)
        
        # Build template variables
        vars_dict = self._build_template_vars(supplier, product, channel, custom_vars)
        
        # Render base template
        subject, body = template.render(**vars_dict)
        
        # Use NIM 550B to personalize/improve the draft
        personalized = await self._personalize_with_nim(
            subject=subject,
            body=body,
            supplier=supplier,
            product=product,
            channel=channel,
        )
        
        # Create draft
        draft = OutreachDraft(
            supplier_id=supplier_id,
            product_id=product_id,
            subject=personalized.get("subject", subject),
            body=personalized.get("body", body),
            channel=OutreachChannel(channel),
            status=OutreachStatus.DRAFT,
        )
        
        draft_id = await add_outreach_draft(draft)
        draft.draft_id = draft_id
        
        logger.info(f"Created outreach draft #{draft_id} for supplier {supplier_id}")
        return draft
    
    def _build_template_vars(
        self,
        supplier: Dict[str, Any],
        product: Dict[str, Any],
        channel: str,
        custom_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Build template variables from supplier/product data."""
        vars_dict = {
            "contact_person": supplier.get("contact_person", "Team"),
            "company_name": supplier.get("company_name", "your company"),
            "platform": supplier.get("platform", "your platform"),
            "product_spec": custom_vars.get("product_spec") if custom_vars else "the product",
            "target_moq": custom_vars.get("target_moq", "500+"),
            "target_price": custom_vars.get("target_price", "competitive"),
            "v2_improvements": custom_vars.get("v2_improvements", "quality improvements"),
            "our_name": custom_vars.get("our_name", "APRS Sourcing"),
            "our_company": custom_vars.get("our_company", "APRS"),
            "our_contact": custom_vars.get("our_contact", "contact@aprs.com"),
        }
        return vars_dict
    
    async def _personalize_with_nim(
        self,
        subject: str,
        body: str,
        supplier: Dict[str, Any],
        product: Dict[str, Any],
        channel: str,
    ) -> Dict[str, str]:
        """Use NIM 550B to personalize the outreach draft."""
        prompt = f"""You are an expert B2B sourcing outreach writer.

Rewrite this outreach message to be more personalized, professional, and effective.

Supplier: {supplier.get('company_name', 'Unknown')}
Platform: {supplier.get('platform', 'Unknown')}
Product: {channel} outreach for product sourcing

Current Subject: {subject}
Current Body:
{body}

Improve by:
1. Making it specific to the supplier's known capabilities
2. Adding clear value proposition for them
3. Making it concise and actionable
4. Maintaining professional, partnership-focused tone

Return ONLY valid JSON:
{{
    "subject": "improved subject line",
    "body": "improved body text"
}}"""
        
        try:
            router = LLMRouter()
            response = await router.chat(
                messages=[
                    {"role": "system", "content": "You are a B2B outreach expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                agent_name="outreach",
                task_type=LLMTaskType.OUTREACH_DRAFTING,
                json_mode=True,
                max_tokens=1000,
            )
            
            import json
            return json.loads(response.text)
        except Exception as e:
            logger.warning(f"NIM personalization failed: {e}")
            return {"subject": subject, "body": body}
    
    async def _get_supplier(self, supplier_id: int) -> Dict[str, Any]:
        """Get supplier from database."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM supplier_profiles WHERE supplier_id = ?", (supplier_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else {}
    
    async def _get_product(self, product_id: str) -> Dict[str, Any]:
        """Get product from database."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM master_products WHERE product_id = ?", (product_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else {}
    
    async def approve_draft(self, draft_id: int, approved_by: str) -> bool:
        """Approve a draft for sending."""
        return await update_outreach_draft(draft_id, status=OutreachStatus.APPROVED.value, approved_by=approved_by)
    
    async def reject_draft(self, draft_id: int, reason: str) -> bool:
        """Reject a draft."""
        return await update_outreach_draft(draft_id, status=OutreachStatus.REJECTED.value, body=reason)
    
    async def send_approved_drafts(self, limit: int = 50) -> List[SendResult]:
        """Send all approved drafts across channels."""
        drafts = await get_pending_outreach_drafts(status=OutreachStatus.APPROVED.value, limit=limit)
        results = []
        
        for draft in drafts:
            result = await self._send_draft(draft)
            results.append(result)
            
            # Update draft status
            if result.success:
                await update_outreach_draft(draft.draft_id, status=OutreachStatus.SENT.value, sent_at=datetime.now(timezone.utc))
            else:
                await update_outreach_draft(draft.draft_id, status=OutreachStatus.DRAFT.value, body=draft.body + f"\n\n--- SEND FAILED: {result.error} ---")
        
        return results
    
    async def _send_draft(self, draft: OutreachDraft) -> SendResult:
        """Send a single draft via its channel."""
        if draft.channel == OutreachChannel.EMAIL:
            return await self._send_email(draft)
        elif draft.channel == OutreachChannel.WHATSAPP:
            return await self._send_whatsapp(draft)
        elif draft.channel == OutreachChannel.INDIAMART_CHAT:
            return await self._send_indiamart_chat(draft)
        else:
            return SendResult(success=False, channel=draft.channel.value, error=f"Unknown channel: {draft.channel}")
    
    async def _send_email(self, draft: OutreachDraft) -> SendResult:
        """Send email via SMTP."""
        try:
            # Get SMTP settings from settings
            smtp_host = getattr(settings, 'smtp_host', 'smtp.gmail.com')
            smtp_port = getattr(settings, 'smtp_port', 587)
            smtp_user = getattr(settings, 'smtp_user', '')
            smtp_pass = getattr(settings, 'smtp_pass', '')
            
            if not smtp_user or not smtp_pass:
                return SendResult(success=False, channel="email", error="SMTP credentials not configured")
            
            # Get supplier email
            supplier = await self._get_supplier(draft.supplier_id)
            to_email = supplier.get("contact_email")
            if not to_email:
                return SendResult(success=False, channel="email", error="Supplier has no email")
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = to_email
            msg['Subject'] = draft.subject
            msg.attach(MIMEText(draft.body, 'plain'))
            
            # Send
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            return SendResult(success=True, channel="email", sent_at=datetime.now(timezone.utc))
            
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return SendResult(success=False, channel="email", error=str(e))
    
    async def _send_whatsapp(self, draft: OutreachDraft) -> SendResult:
        """Send WhatsApp via evolution-go API."""
        try:
            if not settings.evolution_go_url or not settings.evolution_go_apikey:
                return SendResult(success=False, channel="whatsapp", error="evolution-go not configured")
            
            supplier = await self._get_supplier(draft.supplier_id)
            phone = supplier.get("contact_phone")
            if not phone:
                return SendResult(success=False, channel="whatsapp", error="Supplier has no phone number")
            
            # Clean phone number
            phone = phone.replace("+", "").replace("-", "").replace(" ", "")
            if not phone.startswith("91"):
                phone = "91" + phone  # Assume India
            
            # Send via evolution-go API
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "number": f"{phone}@s.whatsapp.net",
                    "text": draft.body,
                }
                headers = {"apikey": settings.evolution_go_apikey}
                async with session.post(
                    f"{settings.evolution_go_url}/message/sendText",
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return SendResult(success=True, channel="whatsapp", message_id=data.get("key", {}).get("id"), sent_at=datetime.now(timezone.utc))
                    else:
                        text = await resp.text()
                        return SendResult(success=False, channel="whatsapp", error=f"HTTP {resp.status}: {text}")
                        
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            return SendResult(success=False, channel="whatsapp", error=str(e))
    
    async def _send_indiamart_chat(self, draft: OutreachDraft) -> SendResult:
        """Send message via IndiaMART chat using WebAgent."""
        try:
            from tools.web_agent import WebAgent
            agent = WebAgent()
            
            supplier = await self._get_supplier(draft.supplier_id)
            profile_url = supplier.get("profile_url")
            if not profile_url:
                return SendResult(success=False, channel="indiamart_chat", error="No profile URL")
            
            # Use WebAgent to send message
            schema = {"message_sent": bool}
            result = await agent.extract_from_url(
                url=profile_url,
                schema=schema,
                task_description=f"Send this message to the supplier via IndiaMART chat: {draft.body}",
            )
            
            if result.get("message_sent"):
                return SendResult(success=True, channel="indiamart_chat", sent_at=datetime.now(timezone.utc))
            else:
                return SendResult(success=False, channel="indiamart_chat", error="Failed to send via IndiaMART chat")
                
        except Exception as e:
            logger.error(f"IndiaMART chat send failed: {e}")
            return SendResult(success=False, channel="indiamart_chat", error=str(e))
    
    async def get_conversation_history(self, supplier_id: int, channel: OutreachChannel, limit: int = 50) -> List[Dict]:
        """Get conversation history for a supplier."""
        return await get_supplier_conversations(supplier_id, limit=limit)
    
    async def log_incoming_message(
        self,
        supplier_id: int,
        channel: OutreachChannel,
        message_text: str,
        message_id: Optional[str] = None,
    ) -> bool:
        """Log incoming message from supplier."""
        return await add_supplier_conversation(
            supplier_id=supplier_id,
            channel=channel.value,
            direction="inbound",
            message_text=message_text,
            message_id=message_id,
        )


async def create_initial_outreach(
    supplier_id: int,
    product_id: str,
    template_id: str = "initial_contact_v1",
    channel: str = "email",
    custom_vars: Optional[Dict[str, str]] = None,
) -> OutreachDraft:
    """Convenience function to create initial outreach draft."""
    engine = OutreachEngine()
    return await engine.generate_draft(supplier_id, product_id, template_id, channel, custom_vars)


if __name__ == "__main__":
    async def test():
        engine = OutreachEngine()
        
        # Test template rendering
        template = get_outreach_template("initial_contact_v1")
        subject, body = template.render(
            contact_person="Mr. Sharma",
            product_spec="Stainless Steel Water Bottle",
            company_name="Test Manufacturing Co.",
            platform="IndiaMART",
            target_moq=500,
            target_price="₹150-200/unit",
            v2_improvements="Leak-proof lid, better insulation",
            our_name="Rahul",
            our_company="APRS Sourcing",
            our_contact="+91-9876543210",
        )
        print("Subject:", subject)
        print("Body:", body[:200])
    
    asyncio.run(test())