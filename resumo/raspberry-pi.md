# Migrar o Atlas para o Raspberry Pi (produção 24/7)

O Pi sempre ligado é o host de produção. A **mesma imagem Docker** roda nele sem
mudança de código — o Pi é ARM e a base `python:3.12-slim` é multi-arch, então o
build é **nativo no Pi** (sem cross-build).

> Recomendado: **Raspberry Pi 4 ou 5**, com **Raspberry Pi OS 64-bit** (arm64) e
> cartão SD bom (ou SSD USB). O bot MVP é leve; o que pesa no futuro é a IA — ver
> [a nota final](#sobre-as-rotinas-com-ia-no-pi).

---

## 1. Preparar o Pi

1. Instale o **Raspberry Pi OS (64-bit)** e conecte o Pi à internet (Wi-Fi ou cabo).
2. Acesse por SSH (ou direto no terminal):
   ```bash
   ssh pi@<ip-do-pi>
   ```
3. Atualize o sistema:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

## 2. Instalar Docker no Pi

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"        # roda docker sem sudo
sudo systemctl enable --now docker     # Docker sobe no boot
# saia e entre de novo no SSH para o grupo 'docker' valer
```

Confirme:
```bash
docker run --rm hello-world
```

## 3. Trazer o projeto e configurar

```bash
git clone <url-do-seu-repo> atlas
cd atlas
cp resumo/.env.example .env
nano .env        # preencha TELEGRAM_TOKEN e ATLAS_ALLOWED_USER_ID
```

> O mesmo `.env` do seu notebook serve — é o mesmo bot e o mesmo ID.

## 4. Subir (build nativo no Pi)

```bash
./scripts/docker-run.sh
```

O primeiro build no Pi demora mais que num PC (é ARM, menos CPU) — normal.
Acompanhe:
```bash
docker compose logs -f atlas
```

Mande `/status` no Telegram para confirmar.

## 5. Garantir o "sempre ligado"

- **Docker no boot:** já feito no passo 2 (`systemctl enable docker`).
- **`restart: always`:** já está no `docker-compose.yml` — o container volta
  sozinho após reboot, queda de energia ou crash.

Testar:
```bash
sudo reboot
# depois que o Pi voltar:
docker compose ps          # atlas deve estar 'running'
```

## 6. Migração do notebook → Pi (sem perder dados)

O estado fica em `./data/atlas.sqlite`. Para levar o histórico junto:

```bash
# no notebook (com o bot parado):
docker compose down
scp data/atlas.sqlite pi@<ip-do-pi>:~/atlas/data/atlas.sqlite
```

Depois suba no Pi (passo 4). **Rode o bot só num lugar por vez** — dois bots com o
mesmo token competem pelas mensagens (long-poll).

---

## Manutenção

| Ação | Comando (no Pi, dentro de `~/atlas`) |
|---|---|
| Ver logs | `docker compose logs -f atlas` |
| Atualizar o código | `git pull && ./scripts/docker-run.sh` (rebuild) |
| Parar | `docker compose down` |
| Backup do banco | `cp data/atlas.sqlite data/atlas.bak.sqlite` |

> **Cartão SD:** SQLite grava com frequência. Para vida longa, prefira **SSD USB**
> ou faça backups periódicos do `data/`.

## Sobre as rotinas com IA no Pi

Os **modelos do Claude rodam na nuvem da Anthropic — nunca no Pi.** O `claude -p`
é só um **cliente leve** que chama o modelo pela rede; o Pi não hospeda modelo nem
faz inferência local. Ou seja, o Pi não precisa de poder de compute para IA — só
de rodar o cliente.

Quando as rotinas com IA entrarem (resumo diário, meta-loop), o que precisa estar
ok no Pi é:
- **Claude Code rodando em arm64** (o cliente `claude -p`);
- **login ativo** no Pi (a credencial da assinatura);
- **rede** para falar com a Anthropic.

O footprint é modesto (I/O de rede, não inferência). Plano: validar `claude -p` no
Pi quando ligarmos as rotinas de IA (E1-05). Rastreado no
[backlog](../docs/roadmap/backlog.md) e no
[ADR-0012](../docs/arquitetura/adr/ADR-0012-empacotamento-docker.md).
