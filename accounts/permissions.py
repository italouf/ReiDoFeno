"""Matriz declarativa de grupos e permissões do sistema.

A autorização real é feita por grupos/permissões (não pelo campo ``perfil``).
Este módulo é a única fonte da verdade usada pelo comando ``seed_groups``.

Permissões são referenciadas por natural key: ``"app_label.codename"``.
Novas fases devem acrescentar suas permissões aqui.
"""

GRUPOS = ("Administrador", "Gestor", "Vendedor", "Cliente")

# O grupo Administrador recebe automaticamente todas as permissões existentes.
GRUPO_ADMINISTRADOR = "Administrador"

PERMISSOES_POR_GRUPO = {
    "Gestor": [
        # Catálogo e cadastros básicos
        "catalog.view_produto",
        "catalog.add_produto",
        "catalog.change_produto",
        "catalog.view_categoria",
        "catalog.add_categoria",
        "catalog.change_categoria",
        "core.view_unidade",
        "core.add_unidade",
        "core.change_unidade",
        # Clientes (gestão)
        "customers.view_cliente",
        "customers.add_cliente",
        "customers.change_cliente",
    ],
    "Vendedor": [
        # Consulta de clientes para pedidos e interações
        "customers.view_cliente",
        # Fase 2/3 (sales, interações) será acrescentada aqui.
    ],
    "Cliente": [
        # Direitos LGPD próprios serão acrescentados na Fase 4.
    ],
}
