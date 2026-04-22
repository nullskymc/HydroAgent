"""
RBAC service for HydroAgent admin console.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from src.database.models import Permission, Role, RolePermissionAssignment, User, UserRoleAssignment

PERMISSIONS = [
    ("dashboard:view", "查看运营总览", "dashboard"),
    ("chat:view", "查看智能对话", "chat"),
    ("history:view", "查看审计记录", "history"),
    ("knowledge:view", "查看知识库", "knowledge"),
    ("knowledge:manage", "管理知识库", "knowledge"),
    ("settings:view", "查看系统设置", "settings"),
    ("settings:manage", "修改系统设置", "settings"),
    ("users:view", "查看用户与角色", "users"),
    ("users:manage", "管理用户与角色", "users"),
    ("assets:view", "查看资产中心", "assets"),
    ("assets:manage", "管理资产中心", "assets"),
    ("alerts:view", "查看告警中心", "alerts"),
    ("alerts:manage", "处理告警事件", "alerts"),
    ("reports:view", "查看报表中心", "reports"),
    ("reports:export", "导出报表", "reports"),
    ("operations:view", "查看运营中心", "operations"),
    ("plans:create", "生成灌溉计划", "operations"),
    ("plans:approve", "审批灌溉计划", "operations"),
    ("plans:execute", "执行灌溉计划", "operations"),
]

ROLE_MATRIX: dict[str, dict[str, object]] = {
    "admin": {
        "name": "系统管理员",
        "description": "拥有全部后台权限。",
        "permissions": [item[0] for item in PERMISSIONS],
    },
    "manager": {
        "name": "运营经理",
        "description": "负责审批、执行、资产与告警管理。",
        "permissions": [
            "dashboard:view",
            "chat:view",
            "history:view",
            "knowledge:view",
            "knowledge:manage",
            "settings:view",
            "assets:view",
            "assets:manage",
            "alerts:view",
            "alerts:manage",
            "reports:view",
            "reports:export",
            "operations:view",
            "plans:create",
            "plans:approve",
            "plans:execute",
        ],
    },
    "operator": {
        "name": "值班操作员",
        "description": "负责生成计划、执行计划和处理告警。",
        "permissions": [
            "dashboard:view",
            "chat:view",
            "history:view",
            "knowledge:view",
            "assets:view",
            "alerts:view",
            "alerts:manage",
            "operations:view",
            "plans:create",
            "plans:execute",
        ],
    },
    "viewer": {
        "name": "只读观察员",
        "description": "只读查看运营数据、资产与报表。",
        "permissions": [
            "dashboard:view",
            "chat:view",
            "history:view",
            "knowledge:view",
            "assets:view",
            "reports:view",
        ],
    },
    "auditor": {
        "name": "审计员",
        "description": "查看审计轨迹并导出审计报表。",
        "permissions": [
            "history:view",
            "reports:view",
            "reports:export",
        ],
    },
}


def ensure_rbac_seed(db: Session):
    permission_map: dict[str, Permission] = {}
    for permission_key, name, category in PERMISSIONS:
        permission = db.query(Permission).filter(Permission.permission_key == permission_key).first()
        if not permission:
            permission = Permission(
                permission_key=permission_key,
                name=name,
                category=category,
                description=f"{name}（{category}）",
            )
            db.add(permission)
            db.flush()
        permission_map[permission_key] = permission

    for role_key, payload in ROLE_MATRIX.items():
        role = db.query(Role).filter(Role.role_key == role_key).first()
        if not role:
            role = Role(
                role_key=role_key,
                name=str(payload["name"]),
                description=str(payload["description"]),
                is_system=True,
            )
            db.add(role)
            db.flush()

        existing = {
            assignment.permission_id
            for assignment in db.query(RolePermissionAssignment).filter(RolePermissionAssignment.role_id == role.id).all()
        }
        expected_permissions = [permission_map[key] for key in payload["permissions"] if key in permission_map]
        for permission in expected_permissions:
            if permission.id not in existing:
                db.add(RolePermissionAssignment(role_id=role.id, permission_id=permission.id))

    db.commit()


def list_roles(db: Session) -> list[Role]:
    ensure_rbac_seed(db)
    return db.query(Role).order_by(Role.id.asc()).all()


def list_permissions(db: Session) -> list[Permission]:
    ensure_rbac_seed(db)
    return db.query(Permission).order_by(Permission.category.asc(), Permission.permission_key.asc()).all()


def set_user_roles(db: Session, user: User, role_keys: Iterable[str], assigned_by: str | None = None):
    ensure_rbac_seed(db)
    normalized = {key for key in role_keys if key}
    roles = db.query(Role).filter(Role.role_key.in_(normalized)).all() if normalized else []
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).delete()
    for role in roles:
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id, assigned_by=assigned_by))
    user.is_admin = "admin" in normalized
    db.commit()
    db.refresh(user)
    return user


def get_user_roles(db: Session, user: User) -> list[Role]:
    ensure_rbac_seed(db)
    refreshed = db.query(User).filter(User.id == user.id).first()
    if not refreshed:
        return []
    return [assignment.role for assignment in refreshed.role_assignments if assignment.role]


def get_user_permission_keys(db: Session, user: User) -> list[str]:
    permissions: set[str] = set()
    for role in get_user_roles(db, user):
        for permission in role.permissions:
            permissions.add(permission.permission_key)
    if user.is_admin:
        permissions.update(item[0] for item in PERMISSIONS)
    return sorted(permissions)


def user_has_permission(db: Session, user: User, permission_key: str) -> bool:
    return permission_key in get_user_permission_keys(db, user)
