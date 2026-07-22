"""Хэширование и проверка паролей — используется gRPC-сессией (grpc_svc/session.py)
и сидом служебного аккаунта (scripts/seed_admin.py). Раньше жило в routers/dependencies.py
вместе с HTTP-специфичными JWT/cookie-хелперами, которые Anki Lite не использует —
вынесено сюда, чтобы не тащить весь HTTP-роутерный слой ради этих двух функций.
"""

import bcrypt


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
