# Atlas — Local (Dev) + Rasp (Pseudo-Prod)

## Acesso

### Local (Dev — sua máquina)
```bash
python -m atlas
# Acesse: http://atlas.local:8080
```

### Rasp (Pseudo-Prod — Tailnet)
```
http://atlas:8080
```

### Setup de aliases (rode uma vez)
```bash
sudo bash -c 'cat >> /etc/hosts << EOF
127.0.0.1 atlas.local
100.74.97.24 atlas
EOF'
```

## Configuração de Produção

1. **Crie `.env` na Rasp** (copie `.env.example`):
   ```bash
   ssh guaxinim@guaxinimserver.tail25c9d8.ts.net
   cd ~/atlas
   cp .env.example .env
   nano .env  # edite com seu TELEGRAM_TOKEN e ATLAS_ALLOWED_USER_ID reais
   ```

2. **Inicie Atlas:**
   ```bash
   source .venv/bin/activate
   python -m atlas
   ```

## Status

- **Hostname Tailscale:** `guaxinimserver.tail25c9d8.ts.net` (IP: 100.74.97.24)
- **Rede Local:** `192.168.86.28` (eth0)
- **Tailscale IP:** `100.74.97.24` (tailscale0)
- **Recurso:** 1GB RAM (suficiente para app + Ollama local)

## Workflow de Desenvolvimento

**Aqui (local):**
1. Edita código em `feat/sua-feature`
2. Commita e faz `git push origin feat/sua-feature`
3. Abre PR no GitHub

**Você valida:**
1. Aprova a PR no GitHub
2. Faz merge em `main`

**Na Rasp (auto-deploy / CD):**
Com o CD ligado (abaixo), o merge em `main` é puxado e aplicado sozinho em até
5 min. Não precisa de pull/restart manual.

## Auto-deploy (CD) na Rasp

Um timer systemd verifica `main` a cada 5 min e, se houver commits novos, faz
`git pull` + (re)instala deps se mudaram + `systemctl --user restart atlas`.

**Dependências de sistema (uma vez, na Rasp):**
```bash
sudo apt install -y pandoc   # export de tradução para EPUB (ADR-0032; .md não precisa)
```

**Instalação (uma vez, na Rasp):**
```bash
cd ~/atlas
chmod +x scripts/atlas-deploy.sh
cp scripts/atlas-deploy.service scripts/atlas-deploy.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now atlas-deploy.timer
```

**Operação:**
```bash
systemctl --user list-timers atlas-deploy.timer   # próxima verificação
journalctl --user -u atlas-deploy -f               # logs do deploy
systemctl --user start atlas-deploy.service        # forçar deploy agora
~/atlas/scripts/atlas-deploy.sh                     # rodar à mão (debug)
```

**Configuração (opcional, no `atlas-deploy.service`):**
- `ATLAS_DEPLOY_REF=main` — branch acompanhada (default `main`).
- `ATLAS_DEPLOY_TRACK=tags` — acompanha a última **tag** em vez de `main`
  (segue à risca a política "prod só roda tags" do CLAUDE.md).

> `main` é protegida por revisão de PR antes do merge, então o auto-deploy de
> `main` aplica só o que já foi revisado/mergeado.

## Troubleshooting

Se Atlas não responder:
```bash
ssh guaxinim@guaxinimserver.tail25c9d8.ts.net
ps aux | grep 'python -m atlas'
tail -50 /tmp/atlas.log
```

Se precisar matar e reiniciar:
```bash
pkill -f 'python -m atlas'
cd ~/atlas && source .venv/bin/activate
python -m atlas  # sem nohup para ver output em tempo real
```
