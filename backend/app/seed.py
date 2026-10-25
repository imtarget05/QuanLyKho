"""Seed demo data into PostgreSQL database.

Idempotent seed that reads sample data from JSON files under sample-data/.
In production, this is blocked via the APP_ENV check.
"""
import asyncio
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.api.routes.auth_utils import get_password_hash
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.cash_sim import CashBalance, CashBox
from app.models.iam import Branch, Capability, Role, RoleCapability, User, UserRole
from app.models.inventory import Asset, Balance, Item, Location, StockLevel
from app.services.approval_controls import DEMO_SUPERVISOR_PIN

# Demo password - used for all seeded demo users.
DEMO_PASSWORD = "DemoPass123!"

# Seeded demo data belongs to the head office (Hội Sở) branch. Locations and
# users are branch-scoped, so a NULL branch_id would make them invisible to
# every non-admin role that resolves its scope from `iam_users.branch_id`.
DEFAULT_BRANCH_CODE = "HO"

REPO_DIR = Path(__file__).resolve().parents[2]  # backend/app -> backend -> repo
SAMPLE_DATA_DIR = Path(os.environ.get("SAMPLE_DATA_DIR", str(REPO_DIR / "sample-data")))


def _load_sample_data(filename: str) -> dict | list:
    """Load sample data from JSON file under sample-data/ directory."""
    path = SAMPLE_DATA_DIR / filename
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def uuid_gen() -> str:
    """Generate UUID as string."""
    return str(uuid.uuid4())


async def _resolve_default_branch(db) -> str | None:
    """Return the default branch id used to scope seeded users and locations.

    Branch data is created by migration 013, so the lookup is best-effort: a
    database that has not been migrated yet simply leaves the scope unset
    instead of failing the whole seed.
    """
    branch_id = await db.execute(
        select(Branch.id).where(Branch.code == DEFAULT_BRANCH_CODE)
    )
    return branch_id.scalar_one_or_none()


async def seed_demo():
    """Seed demo data from sample-data/*.json files.

    Idempotent: skips if data already exists.
    """
    if settings.app_env == "production":
        raise RuntimeError("seed_demo is blocked in production.")

    async with AsyncSessionLocal() as db:
        # --- Roles ---
        # NOTE: add only the MISSING rows. A migration (013) may have already
        # inserted a subset, so "insert only when the table is empty" would
        # silently drop the rest of the catalog on a fresh database.
        roles = [
            Role(code="admin", name="Chủ Quán / Quản Trị Viên (Admin)", description="Toàn quyền hệ thống, giá vốn, giá bán và phân quyền"),
            Role(code="staff", name="Nhân Viên Pha Chế / Quầy (Staff)", description="Tạo phiếu yêu cầu xuất/nhập nguyên liệu và kiểm kê"),
            Role(code="approver", name="Quản Lý Cửa Hàng / Thủ Kho (Approver)", description="Phê duyệt phiếu xuất nhập kho và kiểm kê"),
            Role(code="inventory_manager", name="Quản Lý Danh Mục Kho (Inventory Manager)", description="Quản lý danh mục nguyên liệu, định mức và tồn kho"),
            Role(code="cash_sim_operator", name="Quản Lý Két Tiền Mặt", description="Quản lý sổ quỹ tiền mặt và két sắt"),
            Role(code="integration_admin", name="Quản Trị Tích Hợp", description="Quản lý kết nối hệ thống"),
            Role(code="auditor", name="Kiểm Soát Chất Lượng (Auditor)", description="Đối soát số lượng, hạn sử dụng FEFO và cảnh báo cận date"),
            Role(code="system_admin", name="Quản Trị Hệ Thống (System Admin)", description="Quản trị tài khoản và cấu hình hệ thống"),
        ]
        existing_role_codes = {code for (code,) in (await db.execute(select(Role.code))).all()}
        new_roles = [r for r in roles if r.code not in existing_role_codes]
        if new_roles:
            db.add_all(new_roles)
            await db.commit()
            print(f"Seeded {len(new_roles)} role(s)")

        # --- Capabilities ---
        caps = [
            Capability(code="inventory:create_request", name="Create inventory request"),
            Capability(code="inventory:approve_request", name="Approve inventory request"),
            Capability(code="inventory:manage_catalog", name="Manage inventory catalog"),
            Capability(code="inventory:view_balances", name="View inventory balances"),
            Capability(code="inventory:review", name="Read-only review of inventory and requests"),
            Capability(code="cash:create_request", name="Create cash request"),
            Capability(code="cash:approve_request", name="Approve cash request"),
            Capability(code="cash:reconcile", name="Reconcile cash ledger"),
            Capability(code="cash:view_balances", name="View cash balances"),
            # D2 — quyền quản lý két CHỈ gồm thông tin két (tên/mã/trạng thái),
            # không bao gồm ghi số dư.
            Capability(code="cash:manage_box", name="Manage cash box metadata (name/code/branch)"),
            # D2 — quyền ghi bút toán tài chính (journal điều chỉnh / đảo giao dịch),
            # tách riêng khỏi `cash:manage_box` và `cash:reconcile`.
            Capability(code="cash:post_adjustment", name="Post cash adjustment / reversal journal"),
            Capability(code="approval:view_inbox", name="View approval inbox"),
            Capability(code="activity:view", name="View activity feed"),
            Capability(code="integration:manage", name="Manage integrations"),
            Capability(code="audit:view", name="View audit logs"),
            Capability(code="admin:user_management", name="Manage users"),
            Capability(code="iam:admin", name="Full IAM Administration"),
        ]
        existing_cap_codes = {code for (code,) in (await db.execute(select(Capability.code))).all()}
        new_caps = [c for c in caps if c.code not in existing_cap_codes]
        if new_caps:
            db.add_all(new_caps)
            await db.commit()
            print(f"Seeded {len(new_caps)} capabilit(ies)")

        # --- Role-Capability mappings ---
        mappings = [
            RoleCapability(role_code="staff", capability_code="inventory:create_request"),
            RoleCapability(role_code="approver", capability_code="inventory:approve_request"),
            RoleCapability(role_code="inventory_manager", capability_code="inventory:approve_request"),
            RoleCapability(role_code="admin", capability_code="inventory:approve_request"),
            RoleCapability(role_code="admin", capability_code="inventory:create_request"),
            RoleCapability(role_code="inventory_manager", capability_code="inventory:manage_catalog"),
            RoleCapability(role_code="inventory_manager", capability_code="inventory:view_balances"),
            # Quản lý cửa hàng là checker của ca/phiếu điều chỉnh theo SRS.
            RoleCapability(role_code="inventory_manager", capability_code="inventory:create_request"),
            RoleCapability(role_code="inventory_manager", capability_code="approval:view_inbox"),
            RoleCapability(role_code="staff", capability_code="cash:create_request"),
            RoleCapability(role_code="approver", capability_code="cash:approve_request"),
            RoleCapability(role_code="cash_sim_operator", capability_code="cash:reconcile"),
            RoleCapability(role_code="cash_sim_operator", capability_code="cash:view_balances"),
            # D2 — mapping quyền mới (quản lý thông tin két / ghi bút toán tài chính).
            RoleCapability(role_code="cash_sim_operator", capability_code="cash:manage_box"),
            RoleCapability(role_code="cash_sim_operator", capability_code="cash:post_adjustment"),
            RoleCapability(role_code="approver", capability_code="cash:manage_box"),
            RoleCapability(role_code="approver", capability_code="cash:post_adjustment"),
            RoleCapability(role_code="approver", capability_code="approval:view_inbox"),
            RoleCapability(role_code="staff", capability_code="activity:view"),
            RoleCapability(role_code="approver", capability_code="activity:view"),
            RoleCapability(role_code="inventory_manager", capability_code="activity:view"),
            RoleCapability(role_code="cash_sim_operator", capability_code="activity:view"),
            RoleCapability(role_code="integration_admin", capability_code="integration:manage"),
            RoleCapability(role_code="integration_admin", capability_code="activity:view"),
            RoleCapability(role_code="auditor", capability_code="audit:view"),
            RoleCapability(role_code="auditor", capability_code="inventory:review"),
            RoleCapability(role_code="auditor", capability_code="inventory:view_balances"),
            RoleCapability(role_code="auditor", capability_code="cash:view_balances"),
            RoleCapability(role_code="auditor", capability_code="activity:view"),
            RoleCapability(role_code="staff", capability_code="integration:manage"),
            RoleCapability(role_code="staff", capability_code="inventory:view_balances"),
            RoleCapability(role_code="staff", capability_code="cash:view_balances"),
            RoleCapability(role_code="approver", capability_code="inventory:view_balances"),
            RoleCapability(role_code="approver", capability_code="cash:view_balances"),
            RoleCapability(role_code="approver", capability_code="cash:reconcile"),
            RoleCapability(role_code="admin", capability_code="admin:user_management"),
            RoleCapability(role_code="admin", capability_code="iam:admin"),
            RoleCapability(role_code="admin", capability_code="integration:manage"),
            # D2 — `admin` / `system_admin` phải có đủ quyền quản lý két và
            # ghi bút toán tài chính, nếu không user chỉ có role `admin` bị
            # chặn ở CẢ UI lẫn backend (kể cả luồng tăng quỹ `receipt` vốn
            # giờ yêu cầu `cash:post_adjustment`).
            RoleCapability(role_code="admin", capability_code="cash:manage_box"),
            RoleCapability(role_code="admin", capability_code="cash:post_adjustment"),
            RoleCapability(role_code="system_admin", capability_code="admin:user_management"),
            RoleCapability(role_code="system_admin", capability_code="iam:admin"),
            RoleCapability(role_code="system_admin", capability_code="cash:manage_box"),
            RoleCapability(role_code="system_admin", capability_code="cash:post_adjustment"),
        ]
        existing_pairs = set(
            (
                await db.execute(select(RoleCapability.role_code, RoleCapability.capability_code))
            ).all()
        )
        new_mappings = [m for m in mappings if (m.role_code, m.capability_code) not in existing_pairs]
        if new_mappings:
            db.add_all(new_mappings)
            await db.commit()
            print(f"Seeded {len(new_mappings)} role-capability mapping(s)")

        # --- Users ---
        users_data = list(_load_sample_data("users.json"))
        qa_extra_users = [
            {
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4",
                "username": "demo_admin",
                "display_name_demo": "Phạm Minh Trị (Admin)",
                "roles": ["admin", "staff", "approver"],
            },
            {
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5",
                "username": "demo_approver2",
                "display_name_demo": "Hoàng Quốc Việt (Quản Lý Ca)",
                "roles": ["approver"],
            },
        ]
        all_users_spec = users_data + qa_extra_users
        role_map = {
            "staff": "staff",
            "approver": "approver",
            "auditor": "auditor",
            "admin": "admin",
            "inventory_manager": "inventory_manager",
            "system_admin": "system_admin",
        }
        existing_usernames = set(
            (await db.execute(select(User.username))).scalars().all()
        )
        seen_usernames = set()
        missing_specs = []
        for u in all_users_spec:
            uname = u["username"]
            if uname not in existing_usernames and uname not in seen_usernames:
                seen_usernames.add(uname)
                missing_specs.append(u)
        default_branch_id = await _resolve_default_branch(db)
        if missing_specs:
            password_hash = get_password_hash(DEMO_PASSWORD)
            # D4 — PIN mặc định `123456` CHỈ được gán khi demo mode bật tường
            # minh. Ngoài demo mode user mới không có PIN sẵn: cổng duyệt phải
            # dùng PIN cấu hình / PIN do admin đặt (fail-closed), không tự động
            # dùng PIN demo.
            default_pin_hash = (
                get_password_hash(DEMO_SUPERVISOR_PIN) if settings.is_demo_mode else None
            )
            users = []
            user_roles = []
            for u in missing_specs:
                user = User(
                    id=uuid.UUID(u["id"]),
                    username=u["username"],
                    password_hash=password_hash,
                    pin_hash=default_pin_hash,
                    status="active",
                    display_name_demo=u["display_name_demo"],
                    email=u.get("email"),
                    branch_id=default_branch_id,
                )
                users.append(user)
                for role_key in u.get("roles", []):
                    user_roles.append(
                        UserRole(
                            user_id=uuid.UUID(u["id"]),
                            role_code=role_map.get(role_key, role_key),
                        )
                    )
            db.add_all(users)
            db.add_all(user_roles)
            await db.commit()
            print(f"Seeded {len(users)} users")

        # Sync any newly added roles for existing users (e.g. approver for manager_demo)
        existing_user_roles = set(
            (
                await db.execute(select(UserRole.user_id, UserRole.role_code))
            ).all()
        )
        extra_user_roles = []
        for u in users_data:
            uid = uuid.UUID(u["id"])
            for role_key in u.get("roles", []):
                rc = role_map.get(role_key, role_key)
                if (uid, rc) not in existing_user_roles:
                    extra_user_roles.append(UserRole(user_id=uid, role_code=rc))
                    existing_user_roles.add((uid, rc))
        if extra_user_roles:
            db.add_all(extra_user_roles)
            await db.commit()

        # Backfill the branch for seeded users created before branch scoping
        # existed. Without this, a non-admin seeded user resolves an empty
        # location scope and cannot see any inventory location.
        if default_branch_id is not None:
            seeded_user_ids = [uuid.UUID(u["id"]) for u in all_users_spec]
            unbranched = await db.execute(
                select(User).where(
                    User.id.in_(seeded_user_ids),
                    User.branch_id.is_(None),
                )
            )
            for user in unbranched.scalars().all():
                user.branch_id = default_branch_id
            await db.commit()

        # --- Inventory: Locations ---
        inv_data = _load_sample_data("inventory.json")
        # --- Inventory: Locations (upsert theo id hoặc code — idempotent) ---
        loc_rows = (await db.execute(select(Location))).scalars().all()
        loc_by_code = {loc.code: loc for loc in loc_rows}
        loc_by_id = {str(loc.id): loc for loc in loc_rows}
        new_locations = []
        for loc in inv_data["locations"]:
            existing = loc_by_code.get(loc["code"]) or loc_by_id.get(loc["id"])
            if existing is None:
                new_locations.append(Location(
                    id=uuid.UUID(loc["id"]),
                    code=loc["code"],
                    name=loc["name"],
                    active=True,
                    branch_id=default_branch_id,
                ))
            else:
                existing.code = loc["code"]
                existing.name = loc["name"]
                existing.active = True
                # Backfill the branch for locations seeded before branch scoping
                # existed, otherwise they stay invisible to branch-scoped roles.
                if existing.branch_id is None:
                    existing.branch_id = default_branch_id
        if new_locations:
            db.add_all(new_locations)
        await db.commit()
        print(f"Locations upserted (+{len(new_locations)} mới)")

        # --- Inventory: Items (upsert theo id hoặc sku — idempotent) ---
        item_rows = (await db.execute(select(Item))).scalars().all()
        item_by_sku = {item.sku: item for item in item_rows}
        item_by_id = {str(item.id): item for item in item_rows}
        new_items = []
        for item in inv_data["items"]:
            existing = item_by_sku.get(item["sku"]) or item_by_id.get(item["id"])
            if existing is None:
                new_items.append(Item(
                    id=uuid.UUID(item["id"]),
                    sku=item["sku"],
                    name=item["name"],
                    unit=item["unit"],
                    category=item.get("category"),
                    packaging=item.get("packaging"),
                    cost_price=Decimal(str(item["cost_price"])) if item.get("cost_price") is not None else None,
                    selling_price=Decimal(str(item["selling_price"])) if item.get("selling_price") is not None else None,
                    min_stock=Decimal(str(item["min_stock"])) if item.get("min_stock") is not None else None,
                    tracked_serial=item.get("tracked_serial", False),
                    active=True,
                ))
            else:
                existing.sku = item["sku"]
                existing.name = item["name"]
                existing.unit = item["unit"]
                existing.category = item.get("category")
                existing.packaging = item.get("packaging")
                if item.get("cost_price") is not None:
                    existing.cost_price = Decimal(str(item["cost_price"]))
                if item.get("selling_price") is not None:
                    existing.selling_price = Decimal(str(item["selling_price"]))
                if item.get("min_stock") is not None:
                    existing.min_stock = Decimal(str(item["min_stock"]))
                # Giữ nguyên trạng thái active người dùng đã thiết lập (nếu đã xóa/ẩn thì không tự kích hoạt lại)
        if new_items:
            db.add_all(new_items)
        await db.commit()
        print(f"Items upserted (+{len(new_items)} mới)")

        # --- Inventory: Assets ---
        existing_assets = await db.execute(select(Asset.id))
        if not existing_assets.first():
            loc_result = await db.execute(select(Location.code, Location.id))
            loc_map = {row.code: row.id for row in loc_result.all()}
            item_result = await db.execute(select(Item.sku, Item.id))
            item_map = {row.sku: row.id for row in item_result.all()}

            assets = []
            for asset_data in inv_data.get("assets", []):
                asset = Asset(
                    id=uuid.uuid4(),
                    item_id=item_map[asset_data["sku"]],
                    serial=asset_data["serial"],
                    location_id=loc_map[asset_data["location_code"]],
                    assignee_demo=None,
                    status=asset_data.get("status", "available"),
                )
                assets.append(asset)
            db.add_all(assets)
            await db.commit()
            print(f"Seeded {len(assets)} assets")

        # --- Inventory: Initial Balances ---
        existing_balances = await db.execute(select(Balance.location_id).limit(1))
        if not existing_balances.first():
            loc_result = await db.execute(select(Location.code, Location.id))
            loc_map = {row.code: row.id for row in loc_result.all()}
            item_result = await db.execute(select(Item.sku, Item.id))
            item_map = {row.sku: row.id for row in item_result.all()}

            balances = []
            for bal_data in inv_data.get("initial_balances", []):
                balances.append(Balance(
                    location_id=loc_map[bal_data["location_code"]],
                    item_id=item_map[bal_data["sku"]],
                    quantity=bal_data["quantity"],
                    version=1,
                ))
            db.add_all(balances)
            await db.commit()
            print(f"Seeded {len(balances)} initial balances")

        # --- Inventory: Safety Stock Levels ---
        existing_stock_levels = await db.execute(select(StockLevel.id).limit(1))
        if not existing_stock_levels.first():
            loc_result = await db.execute(select(Location.code, Location.id))
            loc_map = {row.code: row.id for row in loc_result.all()}
            item_result = await db.execute(select(Item.sku, Item.id))
            item_map = {row.sku: row.id for row in item_result.all()}

            stock_levels = []
            for item in inv_data["items"]:
                if "min_qty" in item:
                    # Pilot trà sữa: Min/Max phủ cả quầy + kho mát/khô + kho trung tâm.
                    for loc_code in ("BAR-MAIN", "STORAGE-COOL", "STORAGE-DRY", "KHO-TT"):
                        if loc_code not in loc_map or item["sku"] not in item_map:
                            continue
                        stock_levels.append(StockLevel(
                            id=uuid.uuid4(),
                            location_id=loc_map[loc_code],
                            item_id=item_map[item["sku"]],
                            min_qty=item["min_qty"],
                            max_qty=item.get("max_qty"),
                        ))
            if stock_levels:
                db.add_all(stock_levels)
                await db.commit()
                print(f"Seeded {len(stock_levels)} safety stock levels")

        # --- Cash Simulation ---
        cash_data = _load_sample_data("cash-sim.json")
        existing_cashboxes = await db.execute(select(CashBox.id))
        if not existing_cashboxes.first():
            cashboxes = [
                CashBox(
                    id=uuid.UUID(cb["id"]),
                    code=cb["code"],
                    name=cb["name"],
                    currency=cash_data.get("currency", "VND"),
                    active=True,
                )
                for cb in cash_data["cashboxes"]
            ]
            db.add_all(cashboxes)
            await db.commit()

            cb_result = await db.execute(select(CashBox.id, CashBox.code))
            cb_map = {row.code: row.id for row in cb_result.all()}

            cash_balances = []
            for cb in cash_data["cashboxes"]:
                cash_balances.append(CashBalance(
                    cashbox_id=cb_map[cb["code"]],
                    amount=float(cb.get("opening_balance", "0.00")),
                    version=1,
                ))
            db.add_all(cash_balances)
            await db.commit()
            print(f"Seeded {len(cashboxes)} cashboxes")

        await db.close()
        print("Demo seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed_demo())
