"""Siembra datos para la prueba de carga (se ejecuta dentro de la copia temporal)."""

import asyncio
import os
import random
import sys
from decimal import Decimal

from app.models.bench_product import BenchProduct
from sqlalchemy import delete
from sqlmodel import col

from app.core.permissions import Role
from app.core.security import hash_password
from app.db.session import SessionFactory, engine
from app.models.user import User

USERS = int(os.environ.get("SEED_USERS", "200"))
PRODUCTS = int(os.environ.get("SEED_PRODUCTS", "500"))
BENCH_EMAILS = "bench-%@example.com"


async def cleanup() -> None:
    """Borra las cuentas de la prueba (con LOADTEST_DATABASE_URL la BD no es temporal)."""
    async with SessionFactory() as session:
        result = await session.execute(delete(User).where(col(User.email).like(BENCH_EMAILS)))
        await session.commit()
    await engine.dispose()
    print(f"seed: {result.rowcount} cuentas bench-* borradas")


async def main() -> None:
    hashed = await hash_password(os.environ["LOADTEST_PASSWORD"])
    async with SessionFactory() as session:
        session.add(User(email="bench-admin@example.com", hashed_password=hashed, role=Role.admin))
        for i in range(USERS):
            session.add(User(email=f"bench-user-{i}@example.com", hashed_password=hashed))
        for i in range(PRODUCTS):
            session.add(
                BenchProduct(
                    name=f"Producto {i} {random.choice(['azul', 'rojo', 'verde'])}",  # noqa: S311
                    sku=f"SKU-{i:06d}",
                    price=Decimal(random.randint(100, 99999)) / 100,  # noqa: S311
                    stock=random.randint(0, 500),  # noqa: S311
                    category=random.choice(["books", "games", "music", "tools"]),  # noqa: S311
                )
            )
        await session.commit()
    await engine.dispose()
    print(f"seed: {USERS} usuarios, {PRODUCTS} productos")


asyncio.run(cleanup() if "--cleanup" in sys.argv[1:] else main())
