"""
Admin API Router

Provides endpoints for administrative operations:
- User management (CRUD)
- Audit log access
- System administration
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import users
from app.db_session import get_session
from app.db_models import User, AuditLog, Company
from api.routers.auth import (
    get_current_user, 
    require_admin, 
    require_operator, 
    require_auditor, 
    require_read_admin
)
from app.audit_service import audit_service
from sqlalchemy import desc

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    role: str = Field(default="user", pattern="^(admin|manager|user|auditor|operator)$")
    company: Optional[str] = None
    default_company: Optional[str] = None
    home_location_type: Optional[str] = Field(None, pattern="^(director|market|theater)$")
    home_location_value: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    role: Optional[str] = Field(None, pattern="^(admin|manager|user|auditor|operator)$")
    company: Optional[str] = None
    default_company: Optional[str] = None
    home_location_type: Optional[str] = Field(None, pattern="^(director|market|theater)$")
    home_location_value: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    user_id: int
    username: str
    role: str
    company: Optional[str] = None
    default_company: Optional[str] = None
    home_location_type: Optional[str] = None
    home_location_value: Optional[str] = None
    is_admin: bool
    is_active: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None

    class Config:
        from_attributes = True


class UserList(BaseModel):
    users: List[UserResponse]
    total_count: int


class AuditLogEntry(BaseModel):
    log_id: int
    timestamp: str
    username: Optional[str] = None
    event_type: str
    event_category: str
    severity: str
    details: Optional[str] = None
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLogList(BaseModel):
    entries: List[AuditLogEntry]
    total_count: int


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)
    force_change: bool = False


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/admin/users", response_model=UserList, tags=["Admin"])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    role: Optional[str] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: dict = Depends(require_read_admin)
):
    """
    List all users with optional filtering.

    Requires admin/auditor access.
    """
    with get_session() as session:
        query = session.query(User)

        if role:
            query = query.filter(User.role == role)

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        total_count = query.count()

        query = query.order_by(User.username)
        query = query.offset(offset).limit(limit)

        db_users = query.all()

        user_responses = []
        for u in db_users:
            # Get company names
            company_name = None
            default_company_name = None

            if u.company_id:
                company = session.query(Company).filter(Company.company_id == u.company_id).first()
                company_name = company.company_name if company else None

            if u.default_company_id:
                default_company = session.query(Company).filter(Company.company_id == u.default_company_id).first()
                default_company_name = default_company.company_name if default_company else None

            user_responses.append(UserResponse(
                user_id=u.user_id,
                username=u.username,
                role=u.role,
                company=company_name,
                default_company=default_company_name,
                home_location_type=u.home_location_type,
                home_location_value=u.home_location_value,
                is_admin=u.is_admin,
                is_active=u.is_active,
                created_at=u.created_at.isoformat() if u.created_at else None,
                last_login=u.last_login.isoformat() if u.last_login else None
            ))

        return UserList(users=user_responses, total_count=total_count)


@router.get("/admin/users/{user_id}", response_model=UserResponse, tags=["Admin"])
async def get_user(
    user_id: int,
    current_user: dict = Depends(require_read_admin)
):
    """
    Get a specific user by ID.

    Requires admin/auditor access.
    """
    with get_session() as session:
        u = session.query(User).filter(User.user_id == user_id).first()

        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        # Get company names
        company_name = None
        default_company_name = None

        if u.company_id:
            company = session.query(Company).filter(Company.company_id == u.company_id).first()
            company_name = company.company_name if company else None

        if u.default_company_id:
            default_company = session.query(Company).filter(Company.company_id == u.default_company_id).first()
            default_company_name = default_company.company_name if default_company else None

        return UserResponse(
            user_id=u.user_id,
            username=u.username,
            role=u.role,
            company=company_name,
            default_company=default_company_name,
            home_location_type=u.home_location_type,
            home_location_value=u.home_location_value,
            is_admin=u.is_admin,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
            last_login=u.last_login.isoformat() if u.last_login else None
        )


@router.post("/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Admin"])
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_admin)
):
    """
    Create a new user.

    Requires admin access.
    """
    is_admin = user_data.role == "admin"

    success, message = users.create_user(
        username=user_data.username,
        password=user_data.password,
        is_admin=is_admin,
        company=user_data.company,
        default_company=user_data.default_company,
        role=user_data.role,
        home_location_type=user_data.home_location_type,
        home_location_value=user_data.home_location_value
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Audit user creation
    audit_service.security_event(
        event_type="user_created",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        details={"created_username": user_data.username, "role": user_data.role}
    )

    # Fetch the created user
    with get_session() as session:
        u = session.query(User).filter(User.username == user_data.username).first()

        if not u:
            raise HTTPException(status_code=500, detail="User created but could not be retrieved")

        # Get company names
        company_name = None
        default_company_name = None

        if u.company_id:
            company = session.query(Company).filter(Company.company_id == u.company_id).first()
            company_name = company.company_name if company else None

        if u.default_company_id:
            default_company = session.query(Company).filter(Company.company_id == u.default_company_id).first()
            default_company_name = default_company.company_name if default_company else None

        return UserResponse(
            user_id=u.user_id,
            username=u.username,
            role=u.role,
            company=company_name,
            default_company=default_company_name,
            home_location_type=u.home_location_type,
            home_location_value=u.home_location_value,
            is_admin=u.is_admin,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
            last_login=u.last_login.isoformat() if u.last_login else None
        )


@router.put("/admin/users/{user_id}", response_model=UserResponse, tags=["Admin"])
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: dict = Depends(require_admin)
):
    """
    Update an existing user.

    Requires admin access.
    """
    with get_session() as session:
        u = session.query(User).filter(User.user_id == user_id).first()

        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        # Update fields if provided
        if user_data.username is not None:
            u.username = user_data.username

        if user_data.role is not None:
            u.role = user_data.role
            u.is_admin = user_data.role == "admin"

        if user_data.home_location_type is not None:
            u.home_location_type = user_data.home_location_type

        if user_data.home_location_value is not None:
            u.home_location_value = user_data.home_location_value

        if user_data.is_active is not None:
            u.is_active = user_data.is_active

        # Handle company updates
        if user_data.company is not None:
            company = session.query(Company).filter(Company.company_name == user_data.company).first()
            u.company_id = company.company_id if company else None

        if user_data.default_company is not None:
            default_company = session.query(Company).filter(Company.company_name == user_data.default_company).first()
            u.default_company_id = default_company.company_id if default_company else None

        session.commit()
        session.refresh(u)

        # Audit user update
        audit_service.security_event(
            event_type="user_updated",
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            details={
                "target_user_id": user_id,
                "target_username": u.username,
                "updates": list(user_data.model_dump(exclude_none=True).keys())
            }
        )

        # Get company names for response
        company_name = None
        default_company_name = None

        if u.company_id:
            company = session.query(Company).filter(Company.company_id == u.company_id).first()
            company_name = company.company_name if company else None

        if u.default_company_id:
            default_company = session.query(Company).filter(Company.company_id == u.default_company_id).first()
            default_company_name = default_company.company_name if default_company else None

        return UserResponse(
            user_id=u.user_id,
            username=u.username,
            role=u.role,
            company=company_name,
            default_company=default_company_name,
            home_location_type=u.home_location_type,
            home_location_value=u.home_location_value,
            is_admin=u.is_admin,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
            last_login=u.last_login.isoformat() if u.last_login else None
        )


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    """
    Delete a user.

    Requires admin access.
    """
    # Prevent self-deletion
    if current_user.get("user_id") == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    users.delete_user(user_id)
    return None


@router.post("/admin/users/{user_id}/reset-password", tags=["Admin"])
async def admin_reset_password(
    user_id: int,
    reset_data: PasswordReset,
    current_user: dict = Depends(require_admin)
):
    """
    Reset a user's password.

    Requires admin access.
    """
    with get_session() as session:
        u = session.query(User).filter(User.user_id == user_id).first()

        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        success, message = users.admin_reset_password(
            u.username,
            reset_data.new_password,
            reset_data.force_change
        )

        if not success:
            raise HTTPException(status_code=400, detail=message)

        # Audit password reset
        audit_service.security_event(
            event_type="password_reset_by_admin",
            severity="warning",
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            details={
                "target_user_id": user_id,
                "target_username": u.username,
                "force_change": reset_data.force_change
            }
        )

        return {"message": message}


# ============================================================================
# AUDIT LOG ENDPOINTS
# ============================================================================

@router.get("/admin/audit-log", response_model=AuditLogList, tags=["Admin"])
async def list_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    event_category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    username: Optional[str] = Query(None, description="Filter by username"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: dict = Depends(require_read_admin)
):
    """
    List audit log entries with optional filtering.

    Requires admin/auditor access.
    """
    with get_session() as session:
        query = session.query(AuditLog)

        if event_type:
            query = query.filter(AuditLog.event_type == event_type)

        if event_category:
            query = query.filter(AuditLog.event_category == event_category)

        if severity:
            query = query.filter(AuditLog.severity == severity)

        if username:
            query = query.filter(AuditLog.username.ilike(f"%{username}%"))

        if date_from:
            try:
                from datetime import datetime
                date_obj = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(AuditLog.timestamp >= date_obj)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date_from format. Use YYYY-MM-DD")

        if date_to:
            try:
                from datetime import datetime
                date_obj = datetime.strptime(date_to, '%Y-%m-%d')
                query = query.filter(AuditLog.timestamp <= date_obj)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date_to format. Use YYYY-MM-DD")

        total_count = query.count()

        query = query.order_by(desc(AuditLog.timestamp))
        query = query.offset(offset).limit(limit)

        logs = query.all()

        entries = [
            AuditLogEntry(
                log_id=log.log_id,
                timestamp=log.timestamp.isoformat() if log.timestamp else "",
                username=log.username,
                event_type=log.event_type,
                event_category=log.event_category,
                severity=log.severity,
                details=log.details,
                ip_address=log.ip_address
            )
            for log in logs
        ]

        return AuditLogList(entries=entries, total_count=total_count)


@router.get("/admin/audit-log/event-types", tags=["Admin"])
async def list_audit_event_types(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get list of distinct event types in audit log.

    Requires admin/auditor access.
    """
    with get_session() as session:
        from sqlalchemy import distinct
        types = session.query(distinct(AuditLog.event_type)).all()
        return {"event_types": [t[0] for t in types if t[0]]}


@router.get("/admin/audit-log/categories", tags=["Admin"])
async def list_audit_categories(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get list of distinct event categories in audit log.

    Requires admin/auditor access.
    """
    with get_session() as session:
        from sqlalchemy import distinct
        categories = session.query(distinct(AuditLog.event_category)).all()
        return {"categories": [c[0] for c in categories if c[0]]}
