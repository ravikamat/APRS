"""
core/supplier_models.py — Supplier Profile Schemas for APRS V7.

Pydantic models for supplier profiles, outreach drafts, conversations,
and verification workflows. Used for validation and serialization.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr, field_validator


class SupplierStatus(str, Enum):
    """Supplier verification status."""
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    CONTACTED = "CONTACTED"
    NEGOTIATING = "NEGOTIATING"
    SAMPLE_ORDERED = "SAMPLE_ORDERED"
    SAMPLE_APPROVED = "SAMPLE_APPROVED"
    PO_ISSUED = "PO_ISSUED"
    ARCHIVED = "ARCHIVED"


class OutreachStatus(str, Enum):
    """Outreach draft/status."""
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    HOLD = "HOLD"
    REPLIED = "REPLIED"


class OutreachChannel(str, Enum):
    """Communication channel."""
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    INDIAMART_CHAT = "indiamart_chat"
    ALIBABA_CHAT = "alibaba_chat"
    PHONE = "phone"


class ConversationDirection(str, Enum):
    """Message direction."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ConversationStatus(str, Enum):
    """Conversation message status."""
    RECEIVED = "RECEIVED"
    READ = "read"
    REPLIED = "replied"
    ARCHIVED = "archived"


class ProblemCategory(str, Enum):
    """Problem category classification."""
    FUNCTIONAL = "functional"
    QUALITY = "quality"
    UX = "ux"
    DURABILITY = "durability"
    MISSING_FEATURE = "missing_feature"
    SAFETY = "safety"
    PACKAGING = "packaging"
    SHIPPING = "shipping"
    CUSTOMER_SERVICE = "customer_service"
    OTHER = "other"


class ProblemSeverity(str, Enum):
    """Problem severity."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NUISANCE = "nuisance"


class ProblemStatus(str, Enum):
    """Problem opportunity status."""
    IDENTIFIED = "IDENTIFIED"
    VALIDATED = "VALIDATED"
    IN_PROGRESS = "IN_PROGRESS"
    LAUNCHED = "LAUNCHED"
    ARCHIVED = "ARCHIVED"


class SupplierProfile(BaseModel):
    """Verified supplier profile with GST, verification status, and contact info."""
    
    supplier_id: Optional[int] = None
    product_id: str
    company_name: str = Field(..., min_length=2, max_length=200)
    platform: str = Field(..., pattern=r"^(indiamart|alibaba|exportersindia|tradeindia|direct)$")
    profile_url: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    gst_number: Optional[str] = Field(None, pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z?$")
    moq_estimate: Optional[int] = Field(None, ge=1)
    verification_badge: bool = False
    product_categories: Optional[str] = None
    location: Optional[str] = None
    gst_verified: bool = False
    gst_check_date: Optional[str] = None
    verification_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: SupplierStatus = SupplierStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    
    @field_validator("gst_number")
    @classmethod
    def validate_gst(cls, v: Optional[str]) -> Optional[str]:
        """Validate GST number format (Indian GSTIN)."""
        if v is None:
            return v
        # GSTIN format: 2 digits state + 5 chars PAN + 4 digits + 1 char + 1 char/digit + Z
        # Simplified validation - just check length and alphanumeric
        v = v.upper().strip()
        if len(v) not in (15, 16):  # Allow with/without check digit
            raise ValueError("GST number must be 15 or 16 characters")
        return v
    
    model_config = {"use_enum_values": True}


class OutreachDraft(BaseModel):
    """Email/outreach draft awaiting human approval."""
    
    draft_id: Optional[int] = None
    supplier_id: int
    product_id: str
    subject: str = Field(..., min_length=5, max_length=200)
    body: str = Field(..., min_length=50)
    channel: OutreachChannel = OutreachChannel.EMAIL
    status: OutreachStatus = OutreachStatus.DRAFT
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    
    model_config = {"use_enum_values": True}


class SupplierConversation(BaseModel):
    """Email/WhatsApp/IndiaMART conversation thread."""
    
    conversation_id: Optional[int] = None
    supplier_id: int
    channel: OutreachChannel
    direction: ConversationDirection
    message_text: str
    message_id: Optional[str] = None  # External message ID (WhatsApp, email ID, etc.)
    status: ConversationStatus = ConversationStatus.RECEIVED
    received_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    
    model_config = {"use_enum_values": True}


class ProblemOpportunity(BaseModel):
    """Unmet need/problem extracted from reviews/Q&A/social."""
    
    opportunity_id: Optional[int] = None
    product_id: str
    source: str = Field(..., pattern=r"^(amazon_qa|amazon_reviews|reddit|youtube|flipkart|quora|trustpilot|indiamart_buy_leads)$")
    source_url: Optional[str] = None
    problem_text: str = Field(..., min_length=10)
    problem_category: ProblemCategory = ProblemCategory.OTHER
    severity: ProblemSeverity = ProblemSeverity.MINOR
    frequency_estimate: int = Field(default=1, ge=1, le=10)
    suggested_solution: Optional[str] = None
    market_size_estimate: Optional[str] = None
    competitor_solution: Optional[str] = None
    status: ProblemStatus = ProblemStatus.IDENTIFIED
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    
    model_config = {"use_enum_values": True}


class SupplierSearchResult(BaseModel):
    """Raw supplier search result from WebAgent before verification."""
    
    company_name: str
    platform: str
    profile_url: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    gst_number: Optional[str] = None
    moq_estimate: Optional[int] = None
    verification_badge: bool = False
    product_categories: Optional[str] = None
    location: Optional[str] = None
    
    def to_supplier_profile(self, product_id: str) -> "SupplierProfile":
        """Convert search result to supplier profile."""
        return SupplierProfile(
            product_id=product_id,
            company_name=self.company_name,
            platform=self.platform,
            profile_url=self.profile_url,
            contact_phone=self.contact_phone,
            contact_email=self.contact_email,
            gst_number=self.gst_number,
            moq_estimate=self.moq_estimate,
            verification_badge=self.verification_badge,
            product_categories=self.product_categories,
            location=self.location,
        )


class SupplierVerificationResult(BaseModel):
    """Result of GST and supplier verification."""
    
    supplier_id: int
    gst_valid: bool
    gst_check_date: datetime
    gst_details: Optional[Dict[str, Any]] = None
    company_name_match: bool = False
    address_match: bool = False
    verification_score: float = Field(ge=0.0, le=1.0)
    check_duration_ms: int = 0
    error: Optional[str] = None


class OutreachTemplate(BaseModel):
    """Email/outreach template with variables."""
    
    template_id: str
    name: str
    channel: OutreachChannel
    subject_template: str
    body_template: str
    variables: List[str] = Field(default_factory=list)  # e.g., ["company_name", "product_spec", "moq"]
    
    def render(self, **kwargs) -> tuple[str, str]:
        """Render template with variables."""
        subject = self.subject_template.format(**kwargs)
        body = self.body_template.format(**kwargs)
        return subject, body


# Default outreach templates
DEFAULT_OUTREACH_TEMPLATES = [
    OutreachTemplate(
        template_id="initial_contact_v1",
        name="Initial Supplier Contact",
        channel=OutreachChannel.EMAIL,
        subject_template="Inquiry: {product_spec} - {company_name} sourcing inquiry",
        body_template="""Dear {contact_person},

I hope this email finds you well. I'm writing on behalf of our company to inquire about sourcing {product_spec}.

We are looking for a reliable manufacturer who can produce this product with the following specifications:
- Target MOQ: {target_moq} units
- Target price range: {target_price}
- Key improvements needed: {v2_improvements}

We came across {company_name} on {platform} and were impressed by your profile and product range. We would like to request:

1. Product catalog for similar items
2. MOQ and pricing for {target_moq}+ units
3. Sample cost and lead time
4. Manufacturing capabilities and certifications
5. Payment terms and shipping options

We are serious buyers looking for a long-term partnership. If you can meet our requirements, we can move quickly to sample approval and purchase order.

Looking forward to your response.

Best regards,
{our_name}
{our_company}
{our_contact}""",
        variables=["contact_person", "product_spec", "company_name", "platform", "target_moq", "target_price", "v2_improvements", "our_name", "our_company", "our_contact"],
    ),
    OutreachTemplate(
        template_id="follow_up_v1",
        name="Follow-up After No Response",
        channel=OutreachChannel.EMAIL,
        subject_template="Following up: {product_spec} sourcing inquiry",
        body_template="""Dear {contact_person},

Following up on my previous email regarding {product_spec} sourcing.

We are still very interested in working with {company_name} and would love to hear your thoughts on our inquiry. Even if you cannot meet our exact requirements, we'd appreciate knowing what you can offer.

We are flexible on MOQ and pricing for the right partner and can adjust based on your capabilities.

Please let us know if you need any additional information from our side.

Best regards,
{our_name}
{our_company}""",
        variables=["contact_person", "product_spec", "company_name", "our_name", "our_company"],
    ),
    OutreachTemplate(
        template_id="whatsapp_initial_v1",
        name="WhatsApp Initial Contact",
        channel=OutreachChannel.WHATSAPP,
        subject_template="",  # Not used for WhatsApp
        body_template="""Hi {contact_person}, this is {our_name} from {our_company}. We're interested in sourcing {product_spec} and came across {company_name} on {platform}. 

We're looking for a manufacturer for {target_moq}+ units with improvements: {v2_improvements}. 

Could you share:
1. MOQ & pricing
2. Sample cost & lead time
3. Your manufacturing capabilities

We're serious buyers looking for a long-term partner. Happy to share our detailed specs if interested.

Thanks!""",
        variables=["contact_person", "our_name", "our_company", "product_spec", "company_name", "platform", "target_moq", "v2_improvements"],
    ),
]


def get_outreach_template(template_id: str) -> Optional[OutreachTemplate]:
    """Get outreach template by ID."""
    for template in DEFAULT_OUTREACH_TEMPLATES:
        if template.template_id == template_id:
            return template
    return None


if __name__ == "__main__":
    # Test models
    supplier = SupplierProfile(
        product_id="TEST001",
        company_name="Test Manufacturing Co.",
        platform="indiamart",
        profile_url="https://indiamart.com/test",
        gst_number="27ABCDE1234F1Z5",
        moq_estimate=500,
        verification_badge=True,
        product_categories="Kitchen organizers, storage solutions",
        location="Moradabad, UP",
    )
    print("Supplier:", supplier.model_dump_json(indent=2))
    
    draft = OutreachDraft(
        supplier_id=1,
        product_id="TEST001",
        subject="Test Subject",
        body="Test body",
        channel=OutreachChannel.EMAIL,
    )
    print("Draft:", draft.model_dump_json(indent=2))
    
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