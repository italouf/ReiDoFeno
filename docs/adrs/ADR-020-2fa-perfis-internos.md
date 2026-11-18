# ADR-020 — Autenticação multi-fator (TOTP) para perfis internos

**Fase:** 5
**Status:** Aceita (numeração ajustada após ADR-018 de pagamento manual e ADR-019
de estratégia de backup).

## Contexto

Perfis internos (`Administrador`, `Gestor`, `Emissor Fiscal`, `Financeiro`)
controlam conciliação financeira, emissão/cancelamento de NF-e, ajustes de
estoque e dados pessoais de clientes (LGPD). Autenticação apenas por senha
expõe o sistema a comprometimento por reutilização ou vazamento de credenciais.

## Decisão

1. **Padrão TOTP (RFC 6238) via `django-otp`:** evita dependência de SMS (caro e
   vulnerável a SIM swap) e funciona offline com Google Authenticator, Authy ou
   1Password.
2. **Escopo obrigatório:** `Administrador`, `Gestor`, `Emissor Fiscal`,
   `Financeiro` e superusuários. `Vendedor` e `Cliente` permanecem sem 2FA
   obrigatório nesta etapa para não gerar atrito no lançamento.
3. **Enforcement por middleware + `LoginView`:** `LoginView` direciona perfis
   elegíveis imediatamente após autenticação primária, e
   `OTPRequiredMiddleware` impede acesso a qualquer rota protegida (incluindo
   `/admin/`) sem sessão OTP verificada.
4. **Recuperação por códigos estáticos de uso único:** cada ativação gera 10
   códigos via `otp_static.StaticDevice` para guarda offline pelo operador.
5. **Reset segregado e auditado:** apenas outro `Administrador` pode resetar o
   2FA de um usuário, com registro obrigatório em `LogAuditoria`.
6. **QR code SVG puro:** uso de `qrcode` com `SvgPathImage` elimina compilação
   de Pillow/libjpeg na imagem Docker minimalista.

## Consequências

- Transições financeiras, conciliação e fluxo fiscal ficam protegidos por 2FA.
- Operadores precisam registrar o TOTP no primeiro acesso e guardar os 10
  códigos de backup em cofre/papel seguro.
