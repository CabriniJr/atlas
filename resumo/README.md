# Resumo — colocar o Atlas no ar no Telegram

Guia prático para rodar a **versão funcional (MVP)** do bot. Sem domínio, sem IP
público, sem webhook: o notebook puxa as mensagens via long-poll.

> O que o MVP já faz: registra atividades por mensagem curta (infere domínio —
> físico/estudo/leitura), responde `/status` (registros do dia) e `/ajuda`.
> Só responde a **você** (seu ID do Telegram). Tudo na Camada 0 (zero IA).

---

## 1. Criar o bot no Telegram (BotFather)

1. No Telegram, abra **@BotFather**.
2. Envie `/newbot`, escolha um nome e um username (terminando em `bot`).
3. O BotFather devolve um **token** tipo `123456:ABC-DEF...`. Guarde.

## 2. Descobrir o seu user ID

1. Abra **@userinfobot** no Telegram e envie `/start`.
2. Ele responde com o seu **Id** numérico. Guarde — o bot só responde a esse ID.

## 3. Configurar o ambiente

Na raiz do projeto, copie o exemplo e preencha:

```bash
cp resumo/.env.example .env
# edite .env com seu TELEGRAM_TOKEN e ATLAS_ALLOWED_USER_ID
```

> `.env`, `*.sqlite` e segredos já estão no `.gitignore` — nunca vão pro git.

## 4. Instalar e rodar

Requer **Python 3.12+**.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .

# carrega as variáveis do .env e inicia o bot
set -a; . ./.env; set +a
python -m atlas
```

Você verá `Atlas no ar. Atendendo apenas user_id=...`. Agora, no Telegram:

- mande `treino de perna` → responde `✓ registrado (fisico)`
- mande `estudei álgebra 1h` → `✓ registrado (estudo)`
- mande `/status` → `📊 Hoje: N registro(s).`
- mande `/ajuda` → lista de comandos

Pare com `Ctrl+C`.

## 5. (Opcional) Rodar sempre ligado via systemd

Para o bot subir sozinho e reiniciar (notebook sempre ligado):

```bash
# ajuste os caminhos/usuário no arquivo e instale
cp resumo/atlas-dev.service ~/.config/systemd/user/atlas-dev.service
systemctl --user daemon-reload
systemctl --user enable --now atlas-dev
systemctl --user status atlas-dev
```

> Esta é a base do bot **dev** (roda a branch). O bot **prod** roda uma tag de
> release — ver [política de desenvolvimento](../docs/processos/politica-de-desenvolvimento.md).

---

## Resolução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| `TELEGRAM_TOKEN não definido` | `.env` não carregado | rode `set -a; . ./.env; set +a` |
| Bot não responde | ID errado em `ATLAS_ALLOWED_USER_ID` | confira com @userinfobot |
| `ModuleNotFoundError: atlas` | pacote não instalado | `pip install -e .` no venv |
| Nada chega | token inválido | recrie no @BotFather |

## O que vem depois (roadmap)

Este MVP é a fatia funcional do **M1 — motor mínimo**. Próximos: agendador,
invocador de IA (resumo diário) e o meta-loop. Ver
[amadurecimento](../docs/roadmap/amadurecimento.md) e [backlog](../docs/roadmap/backlog.md).
