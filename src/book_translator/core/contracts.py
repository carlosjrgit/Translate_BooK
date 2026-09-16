"""Protocolos e contratos fundamentais da arquitetura do BookTranslator."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Identifiable(Protocol):
    """Contrato para objetos dotados de ID único."""

    @property
    def id(self) -> str:
        ...


@runtime_checkable
class Serializable(Protocol):
    """Contrato para entidades que podem ser serializadas em dicionários primitivos."""

    def to_dict(self) -> dict[str, Any]:
        ...
