"""Autenticación compartida: hash de contraseñas, JWT HS256 y dependencia FastAPI."""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# bcrypt no mira más allá de 72 bytes y bcrypt 5 lanza ValueError en vez de truncar.
# Dejamos que ese error suba: truncar en silencio haría que dos contraseñas distintas
# con el mismo prefijo de 72 bytes sirvieran indistintamente para entrar.
_BCRYPT_MAX_BYTES = 72

_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    """Lee JWT_SECRET del entorno en cada uso, nunca al importar."""
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET no está definido en el entorno")
    return secret


def hash_password(password: str) -> str:
    """Lanza ValueError si la contraseña pasa de 72 bytes: quien registra debe rechazarla."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    # Una contraseña demasiado larga no puede haber generado ningún hash almacenado,
    # porque hash_password la rechaza: no coincide con nada.
    if len(password.encode()) > _BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(user_id: int | str, email: str, role: str) -> str:
    """Token HS256 con sub/email/role/iat/exp. La expiración sale de JWT_EXPIRE_MINUTES."""
    minutes = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # PyJWT exige que sub sea string
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    """Verifica firma y expiración. Lanza jwt.InvalidTokenError si el token no sirve."""
    return jwt.decode(token, _secret(), algorithms=["HS256"])


@dataclass
class CurrentUser:
    user_id: str
    email: str
    role: str


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Dependencia FastAPI: 401 si falta el header, la firma no valida o el token expiró."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o ausente",  # genérico a propósito: no filtra el motivo
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized
    return CurrentUser(
        user_id=claims["sub"], email=claims.get("email", ""), role=claims.get("role", "")
    )


def user_id_from_request(request: Request) -> str | None:
    """Callback para el middleware de logging: user_id del Bearer token, o None. Nunca lanza."""
    try:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            return None
        return decode_token(token)["sub"]
    except Exception:  # incluye JWT_SECRET ausente: el log no debe tumbar el request
        return None


if __name__ == "__main__":
    os.environ.setdefault("JWT_SECRET", "secreto-de-prueba-solo-para-el-self-check")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/me")
    def me(user: CurrentUser = Depends(require_user)) -> dict:
        return {"user_id": user.user_id, "email": user.email, "role": user.role}

    client = TestClient(app)

    # 0. Una contraseña de más de 72 bytes se rechaza en vez de truncarse en silencio:
    #    si se truncara, cualquier variante con el mismo prefijo entraría igual.
    larga = "a" * 80
    try:
        hash_password(larga)
        raise AssertionError("hash_password debió rechazar una contraseña de más de 72 bytes")
    except ValueError:
        pass
    assert verify_password(larga, hash_password("a" * 72)) is False

    # 1. Round-trip de contraseña.
    hashed = hash_password("barberia123")
    assert verify_password("barberia123", hashed)
    assert not verify_password("barberia124", hashed)
    print("ok  hash/verify password")

    # 2. Token válido decodificable con los claims correctos.
    token = create_access_token(42, "ana@barberflow.local", "client")
    claims = decode_token(token)
    assert claims["sub"] == "42" and claims["email"] == "ana@barberflow.local"
    assert claims["role"] == "client" and claims["exp"] > claims["iat"]
    print("ok  decode_token devuelve sub/email/role")

    # 3. Token válido → 200 con el CurrentUser correcto.
    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.status_code
    assert r.json() == {"user_id": "42", "email": "ana@barberflow.local", "role": "client"}
    print("ok  token válido → 200", r.json())

    # 4. Firma manipulada → 401. Se muta el primer carácter: el último solo lleva bits
    # de relleno que base64url descarta, así que cambiarlo no alteraría la firma.
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"
    assert tampered != token
    r = client.get("/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", r.status_code
    print("ok  token manipulado → 401", r.json())

    # 5. Token expirado → 401 (expiración negativa leída en el momento de emitir).
    os.environ["JWT_EXPIRE_MINUTES"] = "-1"
    expired = create_access_token(42, "ana@barberflow.local", "client")
    os.environ["JWT_EXPIRE_MINUTES"] = "60"
    r = client.get("/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401, r.status_code
    print("ok  token expirado → 401", r.json())

    # 6. Token firmado con otro secreto → 401.
    otro = jwt.encode({"sub": "42"}, "otro-secreto-igual-de-largo-pero-distinto", algorithm="HS256")
    r = client.get("/me", headers={"Authorization": f"Bearer {otro}"})
    assert r.status_code == 401, r.status_code
    print("ok  otro secreto → 401", r.json())

    # 7. Sin header Authorization → 401.
    r = client.get("/me")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", r.status_code
    print("ok  sin header → 401", r.json())

    # 8. user_id_from_request nunca lanza.
    from starlette.datastructures import Headers

    def fake_request(auth: str | None) -> Request:
        raw = [(b"authorization", auth.encode())] if auth else []
        return Request({"type": "http", "headers": Headers(raw=raw).raw, "method": "GET", "path": "/"})

    assert user_id_from_request(fake_request(f"Bearer {token}")) == "42"
    assert user_id_from_request(fake_request("Bearer basura")) is None
    assert user_id_from_request(fake_request(None)) is None
    del os.environ["JWT_SECRET"]
    assert user_id_from_request(fake_request(f"Bearer {token}")) is None  # sin secreto tampoco lanza
    print("ok  user_id_from_request: id con token válido, None con basura")

    print("\nTodos los asserts pasaron.")
