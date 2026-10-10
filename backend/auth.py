"""Who is calling, according to the reverse proxy.

The hackathon proxy authenticates every request and adds X-User-Id (the user's email, a
unique id) and X-User-Name (the full name, percent-encoded). We trust those headers, which
holds only while the app is reachable through the managed address alone: opening the port in
ufw, or setting access control to Disabled, would let anyone send them. See CLAUDE.md.

Locally there is no proxy, so DEV_USER stands in for the header.
"""
from urllib.parse import unquote

from flask import current_app, g, jsonify, request

import db

# Endpoints that answer without a user. Everything else under /api needs one.
PUBLIC_PATHS = {"/api/health"}


def identity():
    """The (email, display name) of the caller, or (None, None)."""
    email = (request.headers.get("X-User-Id") or "").strip().lower()
    name = unquote(request.headers.get("X-User-Name") or "").strip()
    if not email:
        email, name = current_app.config.get("DEV_USER", ""), current_app.config.get("DEV_USER_NAME", "")
        email = (email or "").strip().lower()
    if not email or "@" not in email or len(email) > 254 or any(c.isspace() for c in email):
        return None, None
    return email, name or email.split("@")[0]


def init_app(app):
    @app.before_request
    def load_user():
        g.user = None
        g.via_proxy = bool(request.headers.get("X-User-Id"))
        if not request.path.startswith("/api/") or request.path in PUBLIC_PATHS:
            return None
        email, name = identity()
        if email is None:
            # No proxy header and no DEV_USER: the request did not come through the proxy.
            return jsonify(error="unauthorized"), 401
        g.user = db.upsert_user(email, name)
        return None


def current_user():
    """The caller's user row. Only valid after load_user has run for an /api path."""
    return g.user


def via_proxy():
    """Whether this request carried the proxy's headers, rather than falling back to DEV_USER."""
    return getattr(g, "via_proxy", False)
