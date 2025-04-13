"""
schemas.py

Pydantic models for validating WeChat API responses. Optional but recommended.
"""
# publishing_engine/wechat/schemas.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List

class BaseResponse(BaseModel):
    """Base model for checking WeChat API errors."""
    errcode: int = 0
    errmsg: str = "ok"

class AccessTokenResponse(BaseResponse):
    access_token: Optional[str] = None
    expires_in: Optional[int] = None

class UploadImageResponse(BaseResponse):
    """Response for media/uploadimg API."""
    url: Optional[HttpUrl] = None # Pydantic will validate if it's a URL

class AddMaterialResponse(BaseResponse):
    """Response for material/add_material API."""
    media_id: Optional[str] = None
    url: Optional[HttpUrl] = None # Only present for image uploads

class AddDraftResponse(BaseResponse):
    """Response for draft/add API."""
    media_id: Optional[str] = None

# Add other response models as needed