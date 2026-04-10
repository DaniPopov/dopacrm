"""HTTP middleware package.

Each middleware lives in its own module so the file stays focused. Re-export
the public middleware classes here so route registration code can keep its
imports short:

    from app.api.middleware import AccessLogMiddleware
"""

from app.api.middleware.access_log import AccessLogMiddleware

__all__ = ["AccessLogMiddleware"]
