"""Pure validation tests for commerce request schemas (no database access)."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.routes.commerce import DocumentInput, DocumentLineInput


def test_quote_requires_customer_and_keeps_inventory_optional():
    payload = DocumentInput(
        document_type="quote",
        customer_id=uuid4(),
        lines=[DocumentLineInput(item_id=uuid4(), quantity=Decimal("2"), unit_price=Decimal("10"))],
    )

    assert payload.location_id is None
    assert payload.document_type == "quote"


def test_purchase_requires_supplier_and_selected_location():
    line = DocumentLineInput(item_id=uuid4(), quantity=Decimal("1"), unit_price=Decimal("10"))

    with pytest.raises(ValidationError):
        DocumentInput(document_type="purchase", lines=[line])

    with pytest.raises(ValidationError):
        DocumentInput(document_type="purchase", supplier_id=uuid4(), lines=[line])


def test_payment_due_date_cannot_precede_document_date():
    today = date.today()
    with pytest.raises(ValidationError):
        DocumentInput(
            document_type="sale",
            customer_id=uuid4(),
            location_id=uuid4(),
            document_date=today,
            due_date=today - timedelta(days=1),
            lines=[DocumentLineInput(item_id=uuid4(), quantity=Decimal("1"), unit_price=Decimal("10"))],
        )
