"""OAuth authorization-code flow with state, PKCE and encrypted local tokens."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets
from urllib.parse import urlencode, urlparse

from cryptography.fernet import Fernet, InvalidToken
import httpx
import storage
from social import SPECS

OAUTH = {
    "instagram": ("https://www.instagram.com/oauth/authorize", "https://api.instagram.com/oauth/access_token"),
    "threads": ("https://threads.net/oauth/authorize", "https://graph.threads.net/oauth/access_token"),
    "youtube": ("https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token"),
    "linkedin": ("https://www.linkedin.com/oauth/v2/authorization", "https://www.linkedin.com/oauth/v2/accessToken"),
    "x": ("https://x.com/i/oauth2/authorize", "https://api.x.com/2/oauth2/token"),
}


def cipher():
    key = os.getenv("CREATOROS_TOKEN_KEY")
    if not key:
        raise ValueError("Set CREATOROS_TOKEN_KEY locally before authorizing accounts. See connection setup docs.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise ValueError("CREATOROS_TOKEN_KEY must be a valid Fernet key") from None


def settings(provider):
    prefix = provider.upper()
    client_id = os.getenv(prefix + "_CLIENT_ID")
    secret = os.getenv(prefix + "_CLIENT_SECRET", "")
    redirect = os.getenv(prefix + "_REDIRECT_URI", f"http://127.0.0.1:8000/connections/oauth/{provider}/callback")
    parsed = urlparse(redirect)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")):
        raise ValueError("OAuth redirect must be HTTPS or a local loopback URL")
    if not client_id or (provider != "x" and not secret):
        raise ValueError(f"Configure {prefix}_CLIENT_ID and {prefix}_CLIENT_SECRET locally")
    return client_id, secret, redirect


def begin(connection):
    provider = connection["provider"]
    if provider not in OAUTH:
        raise ValueError("Telegram uses the local session setup script rather than browser OAuth")
    cipher()
    client_id, _, redirect = settings(provider)
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    nonce = secrets.token_urlsafe(32)
    key = "oauth_state:" + hashlib.sha256(state.encode()).hexdigest()
    storage.save("oauth_state", {"connection_id": connection["id"], "provider": provider,
        "verifier": verifier, "cookie_hash": hashlib.sha256(nonce.encode()).hexdigest(),
        "expires": (datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}, key)
    scope = SPECS[provider]["scopes"]
    params = {"client_id": client_id, "redirect_uri": redirect, "response_type": "code", "state": state,
              "scope": scope.replace(" ", ",") if provider in ("instagram", "threads") else scope}
    if provider in ("x", "youtube"):
        params.update(code_challenge=challenge, code_challenge_method="S256")
    if provider == "youtube":
        params.update(access_type="offline", prompt="consent")
    return OAUTH[provider][0]+"?"+urlencode(params), nonce


def consume_state(provider, state, cookie):
    key = "oauth_state:"+hashlib.sha256(state.encode()).hexdigest()
    with storage.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM records WHERE id=? AND kind='oauth_state'", (key,)).fetchone()
        data = json.loads(row[0]) if row else None
        if not data or data["provider"] != provider or data["expires"] < storage.now() or not secrets.compare_digest(data["cookie_hash"], hashlib.sha256((cookie or "").encode()).hexdigest()):
            raise ValueError("OAuth state expired or did not match this browser. Start authorization again.")
        db.execute("DELETE FROM records WHERE id=?", (key,))
    return data


def persist_token(connection_id, data):
    if not isinstance(data.get("access_token"), str) or not data["access_token"]:
        raise ValueError("Provider did not return an access token")
    previous = storage.get("social_token:"+connection_id)
    if previous and not data.get("refresh_token"):
        try:
            data["refresh_token"] = json.loads(cipher().decrypt(previous["encrypted"].encode())) .get("refresh_token")
        except InvalidToken:
            raise ValueError("Stored token cannot be decrypted; restore the key or reauthorize") from None
    expires = data.get("expires_in")
    if expires is not None:
        data["expires_at"] = (datetime.now(timezone.utc)+timedelta(seconds=int(expires))).isoformat()
    storage.save("social_token", {"encrypted": cipher().encrypt(json.dumps(data).encode()).decode()}, "social_token:"+connection_id)


def finish(provider, code, state, cookie, client=None):
    data = consume_state(provider, state, cookie)
    connection = storage.get(data["connection_id"])
    if not connection:
        raise ValueError("Connection no longer exists")
    client_id, secret, redirect = settings(provider)
    payload = dict(grant_type="authorization_code", code=code, client_id=client_id, redirect_uri=redirect)
    if secret and provider != "x":
        payload["client_secret"] = secret
    if provider in ("x", "youtube"):
        payload["code_verifier"] = data["verifier"]
    owned = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    try:
        result = client.post(OAUTH[provider][1], data=payload,
            auth=(client_id, secret) if provider == "x" and secret else None)
        result.raise_for_status()
        token = result.json()
        if provider in ("instagram", "threads"):
            prefix = "ig" if provider == "instagram" else "th"
            host = "https://graph.instagram.com" if provider == "instagram" else "https://graph.threads.net"
            short = token.get("access_token")
            if not short:
                raise ValueError("Provider returned no short-lived token")
            exchanged = client.get(host+"/access_token", params={"grant_type": prefix+"_exchange_token",
                "client_secret": secret, "access_token": short}, headers={"Authorization": "Bearer "+short})
            exchanged.raise_for_status()
            long_token = exchanged.json()
            token = dict(token, **long_token)
            if token.get("user_id") and not connection.get("account_id"):
                connection["account_id"] = str(token["user_id"])
        persist_token(connection["id"], token)
    finally:
        if owned:
            client.close()
    return storage.save("social_connection", dict(connection, status="authorized_unverified", enabled=False,
        next_sync=storage.now(), authorized_at=storage.now()), connection["id"])


def access_token(connection):
    provider = connection["provider"]
    if provider == "telegram":
        if not os.getenv("TELEGRAM_API_ID") or not os.getenv("TELEGRAM_API_HASH"):
            raise ValueError("Configure Telegram API ID, hash, and the local authorized session")
        return "local_session"
    record = storage.get("social_token:"+connection["id"])
    if not record:
        token = os.getenv(provider.upper()+"_ACCESS_TOKEN")
        if not token:
            raise ValueError("Authorize the account or configure its local access token")
        return token
    try:
        data = json.loads(cipher().decrypt(record["encrypted"].encode()))
    except InvalidToken:
        raise ValueError("Cannot decrypt this token. Restore the encryption key or reauthorize.") from None
    if data.get("expires_at", "9999") > (datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat():
        return data["access_token"]
    refresh = data.get("refresh_token")
    if provider in ("instagram", "threads"):
        prefix = "ig" if provider == "instagram" else "th"
        host = "https://graph.instagram.com" if provider == "instagram" else "https://graph.threads.net"
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            refreshed = client.get(host+"/refresh_access_token", params={"grant_type": prefix+"_refresh_token",
                "access_token": data["access_token"]}, headers={"Authorization": "Bearer "+data["access_token"]})
            refreshed.raise_for_status()
            updated = refreshed.json()
        persist_token(connection["id"], updated)
        return updated["access_token"]
    if not refresh or provider not in ("youtube", "x", "linkedin"):
        raise ValueError("Access token expired. Reauthorize the account; existing observations are preserved.")
    client_id, secret, _ = settings(provider)
    payload = dict(grant_type="refresh_token", refresh_token=refresh, client_id=client_id)
    if provider != "x":
        payload["client_secret"] = secret
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        result = client.post(OAUTH[provider][1], data=payload,
            auth=(client_id, secret) if provider == "x" and secret else None)
        result.raise_for_status()
        updated = result.json()
    persist_token(connection["id"], updated)
    return updated["access_token"]


def disconnect(id):
    connection = storage.get(id)
    if not connection:
        raise ValueError("Connection not found")
    with storage.connection() as db:
        db.execute("DELETE FROM records WHERE id=? AND kind='social_token'", ("social_token:"+id,))
    return storage.save("social_connection", dict(connection, enabled=False, status="disconnected"), id)
