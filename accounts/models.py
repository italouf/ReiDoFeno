from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuário do sistema com telefone e perfil de acesso."""

    class Perfil(models.TextChoices):
        ADMINISTRADOR = "administrador", "Administrador"
        GESTOR = "gestor", "Gestor"
        VENDEDOR = "vendedor", "Vendedor"
        CLIENTE = "cliente", "Cliente"

    telefone = models.CharField("telefone", max_length=20, blank=True)
    perfil = models.CharField(
        "perfil",
        max_length=20,
        choices=Perfil.choices,
        default=Perfil.CLIENTE,
        db_index=True,
        help_text="Perfil usado para exibição; a autorização real é por grupos/permissões.",
    )

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.get_username()
