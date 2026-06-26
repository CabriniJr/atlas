---
titulo: Segurança e privacidade
id: ARQ-SEGURANCA
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-26
---

# Segurança e privacidade

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |
| 1.1    | 2026-06-26 | Tech Lead | Multiusuário/credenciais cifradas (ADR-0027, Fases 1–3): cofre Fernet, Credential sem segredo, GitHub device flow + git helper escopado | — |
| 1.2    | 2026-06-26 | Tech Lead | Auth/sessão (ADR-0027, Fase 4): senha local PBKDF2 + login via GitHub; sessão em cookie httpOnly; identidade admin/usuário por request | — |

---

## Modelo de confiança

Sistema **monousuário** rodando no notebook do dono. A maior superfície de risco
não é externa — é o **meta-loop**, único ponto onde código gerado por um modelo
entra no sistema e acaba executado.

## Controles base

- **Acesso restrito:** o bot só responde ao seu próprio ID no Telegram; qualquer
  outro remetente é ignorado.
- **Dados locais:** o SQLite e o repositório ficam no notebook.
- **Segredos fora do versionamento:** tokens (Telegram) e credenciais nunca em git.
- **IA:** o conteúdo das fases de análise vai para o Claude para processamento —
  relevante se uma rotina lidar com dados sensíveis.

## Segurança do meta-loop (a superfície de execução de código)

Decisão completa em [ADR-0003](adr/ADR-0003-seguranca-meta-loop.md). Invariantes:

1. **Inativo por padrão.** Código gerado nasce `ativa: false` e **nunca é
   auto-executado**; ativação exige `/ativar` humano + commit. Invariante, não
   convenção.
2. **Workspace restrito na geração.** O agente (2b) só escreve sob `routines/<nova>/`;
   tools limitadas ao necessário.
3. **Execução contida do `collect`.** Subprocess com timeout; segredos só por
   injeção explícita, nunca por leitura de ambiente implícita.
4. **Análise sem superfície.** Toda fase `analyze` roda single-turn sem tools (2a):
   texto externo malicioso não tem ferramenta para acionar.

## Proteção contra prompt injection

Texto externo (diff, JSON do Librera, mensagens) que vá a um prompt entra em
**blocos delimitados como dados**, nunca como instrução. Reforçado pelo modo 2a
ser tool-less. Ver [ciclo-de-vida-rotina](ciclo-de-vida-rotina.md) e
[ADR-0004](adr/ADR-0004-contrato-collect.md).

## Multiusuário e credenciais cifradas (ADR-0027)

> Evolução para multiusuário com **isolamento total**. Ver
> [ADR-0027](adr/ADR-0027-multiusuario-credenciais.md). Implementado em fases.

- **Cofre de segredos em repouso (Fase 1).** Valores sensíveis (tokens GitHub etc.)
  são cifrados com **Fernet** (AES-128-CBC + HMAC, lib `cryptography`) por
  [`secrets_store`](../../src/atlas/secrets_store.py). Chave mestra em
  `ATLAS_SECRET_KEY` (env) ou `secrets/secret.key` (`0600`, fora do git). Blobs em
  `secrets/credentials/<id>.enc` (`0600`). **Perder a chave = perder os segredos.**
- **Segredo nunca no spec nem no front (Fase 2).** O Kind `Credential` guarda só
  metadados (`provider`, `account`, `scopes`, `status`, `labels.owner`); o token vai
  ao cofre. A UI vê "conectado", nunca o valor.
- **GitHub por device flow (Fase 3).** "Conectar GitHub" usa o **device flow** (sem
  callback público — funciona na Tailnet): o backend faz polling e, ao obter o token,
  **cifra e guarda** como `Credential` do dono. Requer `ATLAS_GITHUB_CLIENT_ID`
  (OAuth App); **fallback**: colar um PAT. O repo-sync autentica clone/fetch com o
  token do dono via header por invocação (`git -c http.extraheader=...`), **sem**
  persistir o token em `.git/config`. O segredo só é descifrado na hora de chamar o
  git; nunca trafega para o front.

- **Auth/sessão por usuário (Fase 4).** Login por **senha local** (verificador
  **PBKDF2-SHA256** com salt, cifrado no cofre — a senha nunca é guardada) ou por
  **GitHub** (device flow). O sucesso abre uma **sessão** (token opaco aleatório, em
  memória, com TTL) entregue em **cookie `atlas_session` httpOnly** (`SameSite=Lax`).
  Cada request é identificado por `_identity()` → `(user, role)`: **admin** quando
  vem o `ATLAS_API_TOKEN`/loopback (retrocompat E0-05), senão o usuário da sessão;
  sem nenhum dos dois ⇒ **401**. O segredo de login não trafega para o front.

## Pendências

- Política de retenção do `texto_cru` em `activities` (dados sensíveis) — backlog.
- Revisão de segurança automatizada de rotinas geradas antes do `/ativar` — a
  avaliar como rotina built-in futura.
- Escopo do store por `labels.owner` (Fase 5); persistência de sessões (hoje em
  memória); rotação/backup da chave mestra do cofre; UI de login no front.
