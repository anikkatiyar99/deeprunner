import re

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def normalize_tenant_id(raw_tenant_id: str) -> str:
    tenant_id = raw_tenant_id.strip()
    pattern = get_settings().allowed_tenant_pattern
    if not re.match(pattern, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID must be 2-64 characters and contain only letters, numbers, underscores, or hyphens.",
        )
    return tenant_id


def resolve_tenant_id(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    if x_tenant_id is None:
        header_name = get_settings().supported_tenant_header
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant is required via the '{header_name}' header.",
        )
    return normalize_tenant_id(x_tenant_id)
