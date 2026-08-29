"""Privacy middleware — records user consent version and sets a cookie.

Each request will have `request.state.consent_version` set to a constant version string
(the value can later be loaded from DB or JWT). The response includes a
`Set-Cookie: consentVersion=...` header so the frontend can check whether the
user has already accepted the privacy policy.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import logging

logger = logging.getLogger(__name__)

class PrivacyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # TODO: replace hard‑coded version with dynamic DB/JWT lookup if needed
        consent_version = "v2024-07"
        # expose to downstream handlers
        request.state.consent_version = consent_version
        
        # --- TEMPORARY DIAGNOSTIC LOGGING (REMOVE AFTER DIAGNOSIS) ---
        client_ip = request.client.host if request.client else "unknown"
        xff = request.headers.get("x-forwarded-for", "none")
        req_id = request.headers.get("x-request-id", "none")
        ua = request.headers.get("user-agent", "none")[:80]
        method = request.method
        path = request.url.path
        
        logger.info(f"[DIAG] req: {method} {path} ip={client_ip} xff={xff} rid={req_id} ua={ua}")
        # -------------------------------------------------------------
        
        # TODO: replace hard‑coded version with dynamic DB/JWT lookup if needed
        consent_version = "v2024-07"
        # expose to downstream handlers
        request.state.consent_version = consent_version
        
        response: Response = await call_next(request)
        
        # --- TEMPORARY DIAGNOSTIC LOGGING (REMOVE AFTER DIAGNOSIS) ---
        logger.info(f"[DIAG] resp: status={response.status_code} path={request.url.path}")
        # -------------------------------------------------------------
        
        # Front‑end reads this cookie (httponly=False)
        response.set_cookie(key="consentVersion", value=consent_version, httponly=False)
        logger.debug("PrivacyMiddleware set consentVersion=%s", consent_version)
        return response
