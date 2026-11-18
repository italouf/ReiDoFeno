"""Utilitários de observabilidade para rotinas de backup."""

import logging

logger = logging.getLogger("reidofeno.backup")


def notificar_falha_backup(*, reason: str, detail: str = "") -> str:
    """Registra falha crítica de backup para captura por logs estruturados e Sentry."""
    motivo = (reason or "unknown").strip()
    detalhe = (detail or "").strip()
    mensagem = f"BACKUP_FAILED: {motivo}"
    if detalhe:
        mensagem = f"{mensagem} ({detalhe})"
    logger.critical(mensagem)
    return mensagem
