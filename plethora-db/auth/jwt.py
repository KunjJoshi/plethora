import jwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from auth.jwks import get_key_for_kid


def _public_key_from_jwk(jwk: dict):
    """Convert a JWK dict to a cryptographic public key PyJWT can use."""
    kty = jwk.get("kty")
    if kty == "EC":
        return ECAlgorithm.from_jwk(jwk)
    if kty == "RSA":
        return RSAAlgorithm.from_jwk(jwk)
    raise ValueError(f"Unsupported JWK key type: {kty}")


_SUPPORTED_ALGS = {"ES256", "RS256"}


def verify_supabase_jwt(token: str) -> dict:
    """
    Verify a Supabase JWT locally using the JWKS public keys published at
    {SUPABASE_URL}/auth/v1/.well-known/jwks.json.

    No network call on the hot path — keys are cached for 1 hour.
    Handles both ES256 (current Supabase default) and RS256.
    Supports all auth providers since Supabase re-signs every token.

    Returns the decoded JWT payload on success.
    Raises ValueError with a user-facing message on any failure.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError:
        raise ValueError("Malformed token.")

    alg = header.get("alg", "")
    if alg not in _SUPPORTED_ALGS:
        raise ValueError(f"Unsupported signing algorithm: {alg}.")

    kid = header.get("kid")
    if not kid:
        raise ValueError("Token is missing key ID (kid).")

    jwk = get_key_for_kid(kid)
    if jwk is None:
        raise ValueError("Token was signed with an unknown key. Please log in again.")

    public_key = _public_key_from_jwk(jwk)

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[alg],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired. Please log in again.")
    except jwt.InvalidAudienceError:
        raise ValueError("Token audience is invalid.")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")

    return payload


def extract_provider(payload: dict) -> str:
    """Return the auth provider (e.g. 'email', 'google', 'github') from a decoded JWT payload."""
    return payload.get("app_metadata", {}).get("provider", "unknown")
