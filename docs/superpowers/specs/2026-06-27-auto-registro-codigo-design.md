---
titulo: Spec de design — Auto-registro de usuários com código compartilhado
id: SPEC-AUTO-REGISTRO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-27
---

# Spec de design — Auto-registro com código compartilhado

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-27 | Tech Lead | Criação — desenho aprovado pelo PO (item 1.4b do hardening) | PO/PM |

---

> Fecha o item **1.4b** do Tema 1 (hardening): UX de cadastro de usuários
> ([ADR-0027](../../arquitetura/adr/ADR-0027-multiusuario-credenciais.md) §Pendências).
> A rotação da chave (1.4a) já está em `main`.

## Problema

Hoje só o **admin** cria usuários, via `POST /_auth/users` (token/bootstrap) — sem
UI. Não há caminho de auto-cadastro. O PO escolheu **auto-registro com código
compartilhado**: o admin define um código secreto; quem o tiver cria a própria conta.

## Decisão

### Backend
- **`ATLAS_SIGNUP_CODE`** (env) define o código. **Se vazio/ausente → auto-registro
  desabilitado** (endpoint recusa). Comparação **constante** (`hmac.compare_digest`).
- `POST /_auth/register {user, password, code}` — **público** (pré-gate), em
  `_handle_auth_post`.
- Helper `_auth_register(store, user, password, code) -> (body, token)` (espelha
  `_auth_login`):
  - registro desabilitado **ou** código inválido → `{ok:false, error}` + HTTP 403.
  - usuário **já existe** → `{ok:false}` (**nunca** sobrescreve) + HTTP 409.
  - senha vazia → `{ok:false}` + HTTP 400.
  - sucesso → `users.create_user(role="member", password=...)` + abre **sessão**
    (mesmo cookie httpOnly do login). Retorna `{ok:true, user, role}` + token.
- **Segurança:** o auto-registrado é **sempre `member`**. `admin` nunca é criado por
  esta via (só token/bootstrap). O código nunca volta para o front.

### Front (tela de login)
- Toggle **"Criar conta"** na tela de login com 3 campos (usuário, senha, código de
  cadastro) + botão. Sucesso = entra direto (sessão por cookie); erro = mensagem.
  *(Estilo mínimo — o overhaul do front, que vem a seguir, retrabalha a UI.)*

## Testes (TDD)
`tests/test_api_auth.py` (espelha os de login):
- código correto → cria `User` `member` + sessão (token resolve).
- código errado → `ok:false`, sem sessão.
- `ATLAS_SIGNUP_CODE` ausente → desabilitado (`ok:false`).
- usuário existente → `ok:false` (não sobrescreve a senha/role).
- papel resultante é sempre `member` (mesmo que o corpo tente `role:admin`).

## Limitações (documentadas)
- Código **compartilhado** (um segredo para todos) — menos rastreável que convite
  individual; recomenda-se um código **longo**. **Sem rate-limit** de brute-force
  nesta fatia → backlog.
- Sem ADR novo (cabe no guarda-chuva do ADR-0027; sem mudança de modelo de dados).

## Fora de escopo (backlog)
- Convite individual por link/token de uso único.
- Rate-limit/lockout no `/_auth/register` e `/_auth/login`.
- UI de admin para listar/remover usuários.
