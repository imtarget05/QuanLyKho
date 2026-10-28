"""Inventory service - nghiệp vụ tồn kho."""

from app.domain.inventory_service import InventoryDomainService


class InventoryService:
    """Dịch vụ nghiệp vụ tồn kho."""

    def __init__(self):
        self.domain_service = InventoryDomainService()

    # CRUD methods will be wired to repositories in follow-up phases
