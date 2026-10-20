"""Rate limiting com resposta HTTP 429 e Retry-After."""

from functools import wraps

from django.http import HttpResponse
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited


def chave_sessao(group, request) -> str:
    """Identifica a sessão; cria uma caso o request ainda não tenha chave."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def limitar_com_429(*, key, rate, method="POST", retry_after=60):
    """Aplica ``ratelimit`` e converte o bloqueio em HTTP 429.

    O ``Retry-After`` é explícito por endpoint (segundos), pois a lib
    retorna 403 por padrão e não informa a janela.
    """

    def decorador(view):
        vista_limitada = ratelimit(
            key=key,
            rate=rate,
            method=method,
            block=True,
        )(view)

        @wraps(view)
        def wrapper(request, *args, **kwargs):
            try:
                return vista_limitada(request, *args, **kwargs)
            except Ratelimited:
                resposta = HttpResponse(
                    "Muitas tentativas. Tente novamente mais tarde.",
                    status=429,
                    content_type="text/plain; charset=utf-8",
                )
                resposta["Retry-After"] = str(retry_after)
                return resposta

        return wrapper

    return decorador
