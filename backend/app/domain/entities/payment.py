"""Pydantic domain entity for payments — the gym's revenue ledger.

Append-only data row. No state machine, no transition methods. The
closest thing to a "transition" is *payment → refund*, modeled as a
fresh row with negative ``amount_cents`` and ``refund_of_payment_id``
pointing back at the original.

``PaymentMethod`` is reused from the Subscription entity — same set of
values across both tables (cash, credit_card, standing_order, other).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.subscription import PaymentMethod


class Payment(BaseModel):
    """One row in the ``payments`` ledger."""

    id: UUID
    tenant_id: UUID = Field(description="Gym this payment belongs to.")
    member_id: UUID = Field(description="Always present — payments are tied to members.")
    subscription_id: UUID | None = Field(
        default=None,
        description=(
            "Optional. Drop-ins / one-off payments don't have a sub. "
            "Subs can be cancelled but the payment record stays."
        ),
    )

    #: Signed. Positive = collected money. Negative = refund row.
    amount_cents: int

    #: Snapshot from ``tenants.currency`` at insert time.
    currency: str

    payment_method: PaymentMethod

    #: When the money actually moved. Backdate-able.
    paid_at: date

    notes: str | None = None

    #: Set on refund rows; points at the original payment.
    refund_of_payment_id: UUID | None = None

    #: Reserved for Phase 5 processor integrations.
    external_ref: str | None = None

    recorded_by: UUID | None = None

    created_at: datetime

    def is_refund(self) -> bool:
        """True iff this row is a refund pointing at another payment."""
        return self.refund_of_payment_id is not None
