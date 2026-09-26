"""Registro de modelos: todo modelo importado aquí es visible para Alembic.

`apigen` añade automáticamente los modelos nuevos antes del marcador.
"""

from app.models.job import Job  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.user import User  # noqa: F401

# [apigen:models]
