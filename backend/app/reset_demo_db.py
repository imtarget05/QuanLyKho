"""Script reset & re-seed dữ liệu mẫu sạch và chuyên nghiệp cho hệ thống BankOps."""
import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.activity import AuditEvent, OutboxEvent
from app.models.approval import ApprovalDecision
from app.models.cash_sim import (
    CashBalance,
    CashBox,
    CashEntry,
    CashJournal,
    CashRequest,
)
from app.models.commerce import (
    CommerceDocument,
    CommerceDocumentLine,
    CommercePayment,
)
from app.models.etl import (
    EtlConnection,
    EtlMappingVersion,
    EtlPipeline,
    EtlRun,
    EtlRunRow,
)
from app.models.iam import User
from app.models.integration import (
    IntegrationConnection,
    IntegrationRun,
    IntegrationStagingRow,
)
from app.models.inventory import (
    Asset,
    AssetLog,
    Balance,
    InventoryEntry,
    InventoryJournal,
    InventoryRequest,
    InventoryRequestLine,
    Item,
    Location,
    LotBalance,
    LotMovement,
    Movement,
    Stocktake,
    StocktakeLine,
)
from app.models.reconciliation import ReconciliationException, ReconciliationRun
from app.models.stock_level import StockLevel
from app.seed import seed_demo


async def reset_demo_database():
    """Xoá toàn bộ dữ liệu giao dịch rác và nạp lại dữ liệu ngân hàng chuẩn mực."""
    print("--- Bắt đầu dọn sạch dữ liệu hệ thống demo ---")
    async with AsyncSessionLocal() as db:
        # 1. Xoá các bảng giao dịch & quan hệ phụ thuộc trước
        await db.execute(delete(CommercePayment))
        await db.execute(delete(CommerceDocumentLine))
        await db.execute(delete(CommerceDocument))
        await db.execute(delete(InventoryEntry))
        await db.execute(delete(InventoryJournal))
        await db.execute(delete(ApprovalDecision))
        await db.execute(delete(LotMovement))
        await db.execute(delete(Movement))
        await db.execute(delete(InventoryRequestLine))
        await db.execute(delete(InventoryRequest))
        await db.execute(delete(StocktakeLine))
        await db.execute(delete(Stocktake))
        await db.execute(delete(StockLevel))
        await db.execute(delete(AssetLog))
        await db.execute(delete(Asset))
        await db.execute(delete(LotBalance))
        await db.execute(delete(Balance))

        await db.execute(delete(CashEntry))
        await db.execute(delete(CashJournal))
        await db.execute(delete(CashRequest))
        await db.execute(delete(CashBalance))

        await db.execute(delete(ReconciliationException))
        await db.execute(delete(ReconciliationRun))

        await db.execute(delete(IntegrationStagingRow))
        await db.execute(delete(IntegrationRun))
        await db.execute(delete(IntegrationConnection))

        await db.execute(delete(EtlRunRow))
        await db.execute(delete(EtlRun))
        await db.execute(delete(EtlMappingVersion))
        await db.execute(delete(EtlPipeline))
        await db.execute(delete(EtlConnection))

        await db.execute(delete(AuditEvent))
        await db.execute(delete(OutboxEvent))

        # 2. Xoá catalog cũ để nạp mới
        await db.execute(delete(Item))
        await db.execute(delete(Location))
        await db.execute(delete(CashBox))
        await db.commit()
        print("Đã xoá sạch các bảng dữ liệu cũ.")

        # 3. Cập nhật tên hiển thị của Users và khôi phục PIN mặc định
        from app.api.routes.auth_utils import get_password_hash
        user_names = {
            "tanmainguyenbinh": "Bình Tân (Chủ Quán / Admin)",
            "demo_maker": "Nguyễn Thị Mai (Pha Chế)",
            "demo_checker": "Trần Văn Quản Lý (Quản Lý Cửa Hàng)",
            "demo_auditor": "Lê Khánh Chi (Kiểm Soát Vận Hành)",
            "demo_admin": "Phạm Minh Trị (Chủ Quán / Admin)",
            "demo_approver2": "Hoàng Quốc Việt (Trưởng Ca)",
        }
        for uname, dname in user_names.items():
            user = (await db.execute(select(User).where(User.username == uname))).scalars().first()
            if user:
                user.display_name_demo = dname
                user.pin_hash = get_password_hash("123456")
        await db.commit()
        print("Đã chuẩn hóa tên nhân sự và mã PIN cửa hàng trà sữa.")

    # 4. Chạy seed_demo để nạp lại từ sample-data sạch
    await seed_demo()

    # 5. Nạp các kết nối mẫu thiết bị cửa hàng F&B
    async with AsyncSessionLocal() as db:
        existing_conns = (await db.execute(select(IntegrationConnection))).scalars().all()
        if not existing_conns:
            conns = [
                IntegrationConnection(
                    id=uuid.uuid4(),
                    type="pos_printer",
                    name="Máy In Bill & POS Quầy Thu Ngân",
                    status="connected",
                    config_json={"endpoint": "https://pos.khotrasua.internal/api/v1/receipts"},
                ),
                IntegrationConnection(
                    id=uuid.uuid4(),
                    type="delivery_hub",
                    name="Cổng Đồng Bộ Đơn Giao Hàng Trực Tuyến",
                    status="connected",
                    config_json={"endpoint": "https://hub.delivery.vn/orders/v1"},
                ),
            ]
            db.add_all(conns)
            await db.commit()
            print("Đã nạp kết nối POS và đối tác giao hàng.")

        # Seed sample ETL Connection & Pipeline
        existing_etl_conn = (await db.execute(select(EtlConnection))).scalars().first()
        if not existing_etl_conn:
            loc = (await db.execute(select(Location))).scalars().first()
            admin_user = (await db.execute(select(User).where(User.username == "demo_admin"))).scalars().first()
            etl_conn = EtlConnection(
                id=uuid.uuid4(),
                type="csv",
                name="Kết nối Tệp CSV/Excel Chi nhánh Bến Thành",
                status="active",
                owner_id=admin_user.id if admin_user else None,
            )
            db.add(etl_conn)
            await db.flush()

            etl_pipe = EtlPipeline(
                id=uuid.uuid4(),
                name="Đồng bộ Tồn kho & Điều chỉnh Quản trị Bến Thành",
                target="balance_adjustment_admin",
                connection_id=etl_conn.id,
                location_id=loc.id if loc else None,
                status="active",
                owner_id=admin_user.id if admin_user else None,
            )
            db.add(etl_pipe)
            await db.flush()

            mv = EtlMappingVersion(
                id=uuid.uuid4(),
                pipeline_id=etl_pipe.id,
                version=1,
                status="published",
                mapping_json=[
                    {"source_field": "sku", "target_field": "sku", "required": True, "transform": "trim_upper"},
                    {"source_field": "target_quantity", "target_field": "target_quantity", "required": False, "transform": "to_float"},
                    {"source_field": "delta_quantity", "target_field": "delta_quantity", "required": False, "transform": "to_float"},
                    {"source_field": "reason", "target_field": "reason", "required": False, "transform": "trim", "default": "Điều chỉnh tồn ETL Admin"},
                ],
                duplicate_policy="reject",
                created_by=admin_user.id if admin_user else None,
                published_at=datetime.now(UTC),
            )
            db.add(mv)
            await db.commit()
            print("Đã nạp ETL Pipeline và Mapping Version mẫu.")

    print("--- Hoàn tất reset và re-seed dữ liệu cửa hàng trà sữa sạch! ---")


if __name__ == "__main__":
    asyncio.run(reset_demo_database())
