"""Protocolos e contratos fundamentais da arquitetura do BookTranslator."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Identifiable(Protocol):
    """Contrato para objetos dotados de ID único."""

    @property
    def id(self) -> str: ...


@runtime_checkable
class Serializable(Protocol):
    """Contrato para entidades que podem ser serializadas em dicionários primitivos."""

    def to_dict(self) -> dict[str, Any]: ...


@runtime_checkable
class PreprocessingPipelineInterface(Protocol):
    """Contrato para o pipeline de pré-processamento e segmentação documental."""

    def process_document(self, document: Any) -> Any: ...

    def process_text(
        self,
        raw_text: str,
        title: str = ...,
        author: str = ...,
    ) -> Any: ...
