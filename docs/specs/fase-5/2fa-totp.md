# 2FA — Autenticação de dois fatores (TOTP) para perfis internos

**Fase:** 5
**Status:** Implementada
**Depende de:** ADR-002 (status financeiro), ADR-020 (2FA para perfis internos).

## Objetivo

Exigir segundo fator TOTP (RFC 6238) via `django-otp` para os perfis que
operam dados financeiros, fiscais, administrativos e LGPD (`Administrador`,
`Gestor`, `Emissor Fiscal`, `Financeiro` e superusuários), preservando login
por senha para `Vendedor` e `Cliente` nesta fase.

## Especificação

1. **Dependências:** `django-otp==1.7.5`, `qrcode==8.2` (QR code em SVG sem
   dependência nativa de Pillow/C).
2. **Grupos obrigatórios (`OTP_REQUIRED_GROUPS`):**
   `Administrador`, `Gestor`, `Emissor Fiscal`, `Financeiro` (+ `is_superuser`).
3. **Middleware (`accounts.middleware.OTPRequiredMiddleware`):**
   - Executado após `OTPMiddleware` e `AxesMiddleware`.
   - Bloqueia acesso autenticado sem `request.user.is_verified()` para usuários
     dos grupos obrigatórios (e superusuários), redirecionando para
     `/accounts/2fa/setup/` (quando não há `TOTPDevice` confirmado) ou
     `/accounts/2fa/verify/` (quando já configurado).
   - Rotas isentas: `/accounts/2fa/`, `/accounts/logout/`, `/static/`,
     `/healthz/`, `/healthz/ip/`.
4. **Setup (`/accounts/2fa/setup/`):**
   - Cria/reutiliza `TOTPDevice(confirmed=False)`, exibe QR code SVG e chave
     Base32 para cadastro manual.
   - Ao validar o primeiro token TOTP, confirma o dispositivo, autentica a
     sessão OTP, gera 10 códigos de backup de uso único (`StaticDevice`),
     audita `accounts.2fa_ativado` e exibe os códigos uma única vez.
5. **Verificação (`/accounts/2fa/verify/`):**
   - Aceita código TOTP de 6 dígitos ou código de backup (`use_backup=true`)
     via `StaticDevice.verify_token` (consumo único).
   - Rate limited por usuário (`10/m`).
6. **Reset administrativo (`resetar_2fa_usuario` / `/accounts/2fa/reset/<pk>/`):**
   - Apenas outro usuário do grupo `Administrador` (ou superusuário) pode
     resetar o 2FA de um usuário alvo; auto-reset é bloqueado.
   - Grava `LogAuditoria` com `acao="accounts.2fa_resetado"`.
