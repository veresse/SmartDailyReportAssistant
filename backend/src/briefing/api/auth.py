"""API 认证中间件与依赖。"""

from fastapi import Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

from briefing.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key_header: str = Security(api_key_header)):
    """验证请求的 API Key。"""
    settings = get_settings()
    
    if not settings.api_secret_key:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, 
            detail="API 写操作认证未配置，默认拒绝访问"
        )
        
    if api_key_header == settings.api_secret_key:
        return api_key_header
        
    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN, detail="API Key 认证失败"
    )

import time
from collections import defaultdict

_rate_limits = defaultdict(list)
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX_REQUESTS = 30

async def rate_limit(api_key: str = Depends(require_api_key)):
    """基于内存的简单限流（按 API Key 限流，每分钟 30 次）。"""
    now = time.time()
    _rate_limits[api_key] = [t for t in _rate_limits[api_key] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limits[api_key]) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    _rate_limits[api_key].append(now)
    return api_key
