"""Exceções do domínio de estoque."""

from django.core.exceptions import ValidationError


class ImutabilidadeViolation(ValidationError):
    """Tentativa de alterar ou excluir um movimento já persistido."""
