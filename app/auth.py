"""Panel logins: CIC_USERS="login:pbkdf2.iterations.salt.hash,..."; passwords never stored in clear."""
import hashlib
import hmac
import os
import secrets

ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2.{ITERATIONS}.{salt}.{digest}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split(".")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def users() -> dict:
    out = {}
    for entry in filter(None, (os.environ.get("CIC_USERS") or "").split(",")):
        login, _, stored = entry.strip().partition(":")
        out[login] = stored
    return out


def csrf_token(login: str) -> str:
    secret = os.environ.get("CIC_SECRET") or "dev-only-secret"
    return hmac.new(secret.encode(), login.encode(), hashlib.sha256).hexdigest()
