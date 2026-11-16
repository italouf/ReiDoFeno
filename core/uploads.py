"""Validação de uploads por extensão, MIME e assinatura binária."""

from django.core.exceptions import ValidationError

ASSINATURAS = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".pdf": (b"%PDF-",),
}

TIPOS_POR_EXTENSAO = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
}


def validar_arquivo(
    arquivo,
    *,
    tipos: set[str],
    extensoes: tuple[str, ...],
    tamanho_maximo: int,
) -> None:
    """Recusa arquivo vazio, grande, com extensão/MIME ou assinatura errada."""
    if arquivo is None:
        return
    if arquivo.size == 0:
        raise ValidationError("Arquivo vazio.")
    if arquivo.size > tamanho_maximo:
        raise ValidationError("Arquivo muito grande (máximo 5 MB).")

    nome = (arquivo.name or "").lower()
    extensao = next(
        (sufixo for sufixo in extensoes if nome.endswith(sufixo)), None
    )
    if extensao is None:
        raise ValidationError("Extensão de arquivo não permitida.")

    content_type = getattr(arquivo, "content_type", "") or ""
    if content_type and content_type not in tipos:
        raise ValidationError("Tipo de arquivo não permitido.")
    if content_type and content_type != TIPOS_POR_EXTENSAO[extensao]:
        raise ValidationError("Tipo do arquivo não corresponde à extensão.")

    posicao = arquivo.tell()
    cabecalho = arquivo.read(8)
    arquivo.seek(posicao)
    if not any(
        cabecalho.startswith(assinatura)
        for assinatura in ASSINATURAS[extensao]
    ):
        raise ValidationError(
            "Conteúdo do arquivo não corresponde ao formato declarado."
        )
