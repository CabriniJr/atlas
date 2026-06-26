---
titulo: ADR-0027 — Multiusuário (isolamento total), auth e credenciais cifradas
id: ADR-0027
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-26
substitui: —
substituido-por: —
---

# ADR-0027 — Multiusuário (isolamento total), auth e credenciais cifradas

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-25 | Tech Lead | Proposta — identidade, isolamento por usuário, credenciais cifradas, GitHub device flow, Claude compartilhado | — |
| 0.2    | 2026-06-26 | Tech Lead | Fase 3 implementada (`github_auth`: device flow + PAT + git helper escopado; endpoints `/_github/*`; repo-sync autentica por dono) | — |
| 0.3    | 2026-06-26 | Tech Lead | Fase 4 implementada (`users`/`sessions`: senha local PBKDF2 + login via GitHub; cookie httpOnly; `_identity` na API; admin via token/loopback) | — |
| 1.0    | 2026-06-26 | Tech Lead | Fase 5 implementada (`scoping`: isolamento por `labels.owner` em list/get/put/delete + migração no boot). Épico completo (Fases 1–5) → **aceito** | PO/PM |

---

## Status
`aceito` — implementação **faseada concluída** (Fases 1–5, ver §Fases). Decisões
tomadas com o PO: isolamento **total** por usuário; Claude via **assinatura
compartilhada do host**; GitHub via **device flow**; credenciais **cifradas em
repouso**.

## Contexto

Hoje o Atlas é single-user: auth da API é um token único (`ATLAS_API_TOKEN`) ou
loopback, e todos os recursos são globais. O PO pediu **multiusuário**: cada pessoa
loga e usa suas próprias credenciais (ex.: conectar o GitHub pelo web e o repo-sync
passar a funcionar com a conta dela), com **isolamento total** entre usuários, e
**criptografia/segurança** nos dados sensíveis.

Restrição técnica chave: o **`claude` CLI** (motor de IA, [ADR-0001](ADR-0001-ia-em-dois-modos.md)/
[ADR-0022](ADR-0022-motor-de-ia-plugavel.md)) autentica por **assinatura, por máquina**
— não há token de assinatura por-usuário injetável por chamada. Por isso o Claude
fica **compartilhado** (login do host), com **atribuição de custo por usuário/agente**
([E7-44](../../roadmap/backlog.md)).

## Decisão

### 1. Identidade — Kind `User`
Usuário é um objeto ([P11](../../visao/principios.md)). `spec`: `display_name`,
`role` (`admin`|`member`). Segredo de login (hash de senha **ou** GitHub OAuth) **não**
fica no spec — vai cifrado no cofre (§4). Há um `admin` inicial (compatível com o
token/loopback atual: o portador do `ATLAS_API_TOKEN` age como admin).

### 2. Auth/sessão
Login → **sessão** (token opaco aleatório, cookie httpOnly) → identifica o usuário em
cada request. O `ATLAS_API_TOKEN`/loopback continua válido como **admin** (retrocompat
e operação por script). Sem sessão nem token ⇒ 401.

### 3. Isolamento total por usuário
Todo recurso ganha dono: `labels.owner=<user>`. O `ResourceStore`/API **escopam por
dono** — `list/get/put/delete` só enxergam/alteram recursos do usuário da sessão; o
`admin` enxerga tudo. Recursos atuais (sem owner) são migrados para o admin/usuário
primário. Kinds de sistema (Doc de ADR, kindref) podem ser **globais** (read-only a
todos) por um marcador (`labels.scope=system`).

### 4. Credenciais cifradas em repouso (segurança)
- **Kind `Credential`** guarda só **metadados** (`provider`: github|…, `owner`,
  `status`, `scopes`, `criado_em`) — **nunca o segredo** no spec.
- O **valor secreto** (token GitHub etc.) é cifrado por um **cofre** (`secrets_store`)
  com **Fernet** (AES-128-CBC + HMAC, lib `cryptography`). Chave mestra em
  `ATLAS_SECRET_KEY` (env) ou arquivo `secrets/secret.key` (perms `0600`, fora do git).
- Blobs cifrados em `secrets/credentials/<id>.enc` (`0600`) — nunca commitados.
- Em uso: o backend descifra só na hora de chamar o provider; segredos **não** trafegam
  para o front (a UI vê status "conectado", não o token).

### 5. GitHub — device flow (por usuário)
"Conectar GitHub" inicia o **device flow** (sem callback público — funciona na Tailnet):
backend pede `device_code`/`user_code`, o usuário abre `github.com/login/device` e cola
o código; o backend faz polling e, ao obter o `access_token`, **cifra e guarda** como
`Credential` daquele usuário. O repo-sync passa a usar o token do dono do Repo via o
git credential helper escopado. Requer um **GitHub OAuth App** (client_id público em
`ATLAS_GITHUB_CLIENT_ID`); **fallback**: colar um PAT quando o app não estiver
configurado.

### 6. Claude — assinatura compartilhada do host
Todos usam o login Claude da máquina (atual). Custo é **atribuído por usuário/agente**
no `status` (E7-44). (Login Claude por-usuário via `CLAUDE_CONFIG_DIR` + device flow
fica registrado como evolução possível, fora do escopo agora.)

## Alternativas consideradas
| Tema | Alternativa | Veredito |
|---|---|---|
| Claude | API key por usuário | rejeitada — billing por token fere P1; modo code não usa |
| Claude | login por usuário (CLAUDE_CONFIG_DIR) | adiada — complexa; host compartilhado atende |
| GitHub | OAuth App (callback) | adiada — exige ingress público (Funnel); device flow evita |
| GitHub | só PAT colado | é o **fallback**; device flow é a UX preferida |
| Isolamento | escopo por `labels.owner` na API | **escolhida** — incremental sobre o store atual |
| Isolamento | namespace/DB por usuário | rejeitada — migração e custo altos |
| Cripto | rolar à mão / só perms de arquivo | rejeitada — usar `cryptography`/Fernet (padrão) |

## Consequências
- **Positivas:** cada usuário opera com suas credenciais; dados sensíveis cifrados em
  repouso; isolamento real; base p/ o uso multiusuário em produção.
- **Negativas / custos:** +deps (`cryptography`); auth/sessão e escopo por dono tocam
  toda a API (risco — faseado e testado); gestão da chave mestra (perda ⇒ perda dos
  segredos cifrados); migração dos recursos atuais para um dono.
- **Impacto:** estende o modelo de auth (E0-05) e o `ResourceStore` ([ADR-0015](ADR-0015-core-api-de-objetos.md));
  aplica P11 (User/Credential como objetos). Atualiza [seguranca](../seguranca.md).

## Fases (implementação incremental, mergeável)
1. **Cofre cifrado** (`secrets_store`, Fernet) + dep `cryptography` — fundação segura,
   não-destrutiva, com testes. **(esta entrega)**
2. **Kind `User`** + **Kind `Credential`** (metadados) — objetos, não-destrutivo.
3. **GitHub device flow** (start/poll) → grava `Credential` cifrada + git helper escopado.
   **(feito)** — [`github_auth.py`](../../../src/atlas/github_auth.py): `start_device_flow`/
   `poll_access_token`/`complete_device_login`, fallback `connect_via_pat`,
   `token_for_owner` + `git_auth_args`. Endpoints `POST /_github/device/start|poll`,
   `/_github/pat`. O repo-sync resolve o token do dono (`labels.owner`) e autentica
   clone/fetch via `gitcmd.git(..., auth_args=...)` (header por invocação, sem persistir).
   Config: `ATLAS_GITHUB_CLIENT_ID`. UI "🔗 Conectar GitHub" no front liga isto à conta
   do usuário logado (Fase 6); o dono vem da sessão (Fase 4) ou `ATLAS_DEFAULT_OWNER`.
4. **Auth/sessão** (login) mantendo admin via token/loopback. **(feito)** —
   [`users.py`](../../../src/atlas/users.py) (senha local: verificador PBKDF2 cifrado
   no cofre) e [`sessions.py`](../../../src/atlas/sessions.py) (token opaco em memória
   + TTL). Na API, `_identity()` resolve `(user, role)` de admin (token/loopback) ou da
   sessão (cookie `atlas_session` httpOnly); `_auth()` exige um dos dois. Endpoints
   públicos: `POST /_auth/login`, `/_auth/logout`, `/_auth/github/start|poll`,
   `GET /_auth/me`; `POST /_auth/users` (admin cria usuário + senha — bootstrap). O
   login via GitHub reusa o device flow (Fase 3): resolve o username,
   cria o `User`, salva a credencial e abre sessão. A **UI de login** no front (Fase 6)
   consome estes endpoints. **Pendente:** persistência de sessões (hoje em memória).
5. **Isolamento por `labels.owner`** no store/API + migração dos recursos atuais.
   **(feito)** — [`scoping.py`](../../../src/atlas/scoping.py): `can_see`/`can_write`/
   `stamp_owner`/`visible`. A API escopa **list/get/put/delete** pelo dono da sessão
   (admin vê tudo; recurso alheio ⇒ 404; `scope=system` global read-only; create
   carimba o dono). Migração no boot ([`app.py`](../../../src/atlas/app.py),
   `migrate_unowned`) leva os recursos antigos para `ATLAS_DEFAULT_OWNER`. O escopo
   roda na camada **HTTP**; usos internos do store (sync/rotinas/scheduler) não são
   escopados.
6. **UI multiusuário no front.** **(feito)** — tela de login (senha + Conectar com
   GitHub + token avançado), chip de usuário + logout, botão "🔗 Conectar GitHub"
   (credencial p/ repo-sync). `init()` checa `GET /_auth/me` e abre o login no 401.
   Local (loopback) segue admin sem tela. ([`index.html`](../../../src/atlas/dashboard/index.html),
   [`main.js`](../../../src/atlas/dashboard/main.js), [`style.css`](../../../src/atlas/dashboard/style.css)).

## Pendências
- Definir UX de cadastro/convite de usuários (admin cria? auto-registro?).
- Rotação da chave mestra e backup seguro.
- Escopo fino de kinds globais (system) vs por-usuário.
- Login Claude por-usuário (evolução, se necessário).
