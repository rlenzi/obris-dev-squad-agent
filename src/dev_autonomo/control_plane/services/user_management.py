"""Servicos de gestao de users + memberships.

Encapsula:
- Criacao atomica de User + ClientMembership (admin platform onboarding).
- Convite de user dentro de um tenant existente (client_admin).
- Update parcial e listagem.

Atomicidade: tudo num unico session.flush() — em erro a transacao reverte.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.auth import hash_password
from dev_autonomo.db.models import Client, ClientMembership, User


class UserManagementError(Exception):
    """Erro funcional de gestao de users (email duplicado, role invalida, etc)."""


async def create_user_for_client(
    *,
    session: AsyncSession,
    client_id: UUID,
    email: str,
    full_name: str,
    password: str,
    role: UserRole = UserRole.CLIENT_ADMIN,
) -> tuple[User, ClientMembership]:
    """Cria User + ClientMembership ligando ao cliente em uma transacao.

    Usado pelo system_admin no wizard de novo cliente OU pelo client_admin
    convidando users do proprio tenant.

    Raises:
        UserManagementError: se email ja existe, cliente nao encontrado, etc.
    """
    # Cliente existe?
    client = (
        await session.execute(select(Client).where(Client.id == client_id))
    ).scalar_one_or_none()
    if client is None:
        raise UserManagementError(f"cliente {client_id} nao encontrado.")

    # Email duplicado?
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        # Se ja tem membership nesse cliente, erro.
        existing_mem = (
            await session.execute(
                select(ClientMembership).where(
                    ClientMembership.client_id == client_id,
                    ClientMembership.user_id == existing.id,
                )
            )
        ).scalar_one_or_none()
        if existing_mem is not None:
            raise UserManagementError(
                f"email '{email}' ja tem acesso a esse cliente."
            )
        # User existe mas sem membership aqui — cria so a membership.
        new_mem = ClientMembership(
            client_id=client_id, user_id=existing.id, role=role
        )
        session.add(new_mem)
        await session.flush()
        return existing, new_mem

    # Cria user + membership atomicamente
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_system_admin=False,
        active=True,
    )
    session.add(user)
    await session.flush()

    membership = ClientMembership(
        client_id=client_id, user_id=user.id, role=role,
    )
    session.add(membership)
    await session.flush()

    return user, membership


async def list_users_for_client(
    *, session: AsyncSession, client_id: UUID
) -> list[tuple[User, ClientMembership]]:
    """Lista (user, membership) de todos os users do tenant.

    Ordem: created_at ascendente (primeiro user criado primeiro).
    """
    rows = (
        await session.execute(
            select(User, ClientMembership)
            .join(ClientMembership, ClientMembership.user_id == User.id)
            .where(ClientMembership.client_id == client_id)
            .order_by(User.created_at.asc())
        )
    ).all()
    return [(u, m) for u, m in rows]


async def update_client_user(
    *,
    session: AsyncSession,
    client_id: UUID,
    user_id: UUID,
    role: UserRole | None = None,
    active: bool | None = None,
) -> tuple[User, ClientMembership]:
    """Update parcial de role/active de um user no tenant."""
    row = (
        await session.execute(
            select(User, ClientMembership)
            .join(ClientMembership, ClientMembership.user_id == User.id)
            .where(
                ClientMembership.client_id == client_id,
                User.id == user_id,
            )
        )
    ).first()
    if row is None:
        raise UserManagementError(
            f"user {user_id} nao tem membership no cliente {client_id}."
        )
    user, membership = row
    if role is not None:
        membership.role = role
    if active is not None:
        user.active = active
    await session.flush()
    return user, membership


def generate_password(length: int = 16) -> str:
    """Gera senha aleatoria com chars alfanumericos + simbolos seguros.

    Usado pelo botao 'Gerar' do wizard admin. Excluidos chars que confundem
    visualmente (0/O, 1/l, etc) pra reduzir erro de transcricao.
    """
    import secrets

    alphabet = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ"  # sem I, O
        "abcdefghijkmnpqrstuvwxyz"  # sem l, o
        "23456789"                  # sem 0, 1
        "!@#$%&*-_+="
    )
    return "".join(secrets.choice(alphabet) for _ in range(length))
