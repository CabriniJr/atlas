---
titulo: ADR-0056 — Nuvem pessoal: "Local ou Nuvem?" no download e a loja servindo o OneDrive
id: ADR-0056
status: aceito
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-10-03
substitui: —
substituido-por: —
---

# ADR-0056 — Nuvem pessoal: "Local ou Nuvem?" e a loja servindo o OneDrive

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-10-03 | Tech Lead | Proposta e aceite (PO escolheu "perguntar por jogo" + "rclone mount + Ownfoil serve") | PO |

---

## Status
`aceito` — implementa a **frente D** da visão de nuvem pessoal e fecha o "nó
técnico central" dela. Depende do [ADR-0055](ADR-0055-systemd-dono-dos-containers.md)
(o mount e a loja são units) e revisa um detalhe do
[ADR-0052](ADR-0052-ownfoil-tinfoil-via-funnel.md) (o `:Z` do acervo).

## Contexto

O PO quer: jogo baixado **sobe pro OneDrive** e o **Ownfoil puxa de lá**, para o
Switch instalar sem o jogo ocupar disco no PC. Havia 916 GiB livres na nuvem
(1 TiB, 113 usados) e `onedrive:Jogos/Switch` já existia da reorg de julho.

**Decisões do PO neste ADR:**
- **"Perguntar por jogo"**: a confirmação do download passa a ser *onde*, não
  *se*. `local` mantém no PC; `nuvem` sobe e libera o disco.
- **`rclone mount` + Ownfoil serve**: o PC é a ponte; o Switch baixa através dele.
  As alternativas (baixar sob demanda, links diretos do OneDrive) foram
  descartadas — a última é frágil com arquivo grande, como a própria nota de
  julho já registrava.

## Decisão

### 1. A nuvem entra *dentro* do acervo
`onedrive:Jogos/Switch` é montado em `~/Games/Switch/Nuvem`, subpasta do acervo
que a loja **já** serve. O Ownfoil não ganhou uma linha de código: para ele, a
nuvem é mais uma pasta. Unit `atlas-nuvem.service` (`nuvem/mount.py`).

### 2. Dois bloqueios de SELinux/mount, medidos e resolvidos

**`:Z` no acervo é incompatível com mount dentro dele.** O `:Z` faz o podman
relabelar **recursivamente**; ao chegar no FUSE read-only ele falha e o container
nem sobe:

```
Error: lsetxattr(label=...container_file_t...) /home/guaxinim/Games/Switch/Nuvem:
read-only file system
```

O acervo passa a `:ro` **sem** `:Z`. Como ninguém mais rotula, `rotular_acervo`
faz `chcon -R -l s0 -t container_file_t`. O **`-l s0` é essencial**: categorias
MCS sobrando de um `:Z` antigo (`s0:c30,c41`) não casam com as do container e o
acesso é negado. Isso é feito **em código**, não "lembrando de rodar o chcon".

**Mount criado depois do container não aparece dentro dele.** Os volumes são
`propagation=rprivate` — o container vê a pasta vazia. Como o `-v` é *rbind*, o
submount que já existe **no start** entra. Daí `Type=notify` no mount (o systemd
só marca "started" depois de montar, e a doc do rclone promete que quem depende
vê tudo) + `After=`/`Wants=atlas-nuvem.service` na unit da loja, e
`garantir_no_ar` rotula e monta **antes** de subir o container. `Wants=`, não
`Requires=`: OneDrive fora do ar não derruba a loja, que segue servindo o local.

### 3. Subir usa `rclone move`, não `copy` + `rm`
O `move` confere cada arquivo no destino **antes** de remover a origem; só sai do
disco o que chegou. Um `rm` cego depois de um upload truncado perderia o jogo.
Além disso, o `--delete-empty-src-dirs` **não** apaga a raiz da origem — a sobra
não é cosmética, porque `arquivar_ausentes` olha `os.path.exists` e a pasta vazia
faria o jogo parecer local. `_remover_se_vazio` usa `os.rmdir`, que **falha** se
houver qualquer coisa dentro.

### 4. Travas de segurança
- **Integridade primeiro**: o monitor só sobe se `integridade == ok`. Subir e
  apagar o local a partir de um download corrompido perderia o jogo nas duas pontas.
- **Upload em thread**: o monitor é uma thread única; um jogo de 25 GB bloquearia
  o progresso de *todos* os downloads.
- **Pasta vazia não é "estar no disco"** (`servico._tem_conteudo`): desinstalar um
  jogo costuma deixar o diretório, e tratar isso como presente era parte do bug
  "jogo desinstalado ainda aparece".

## Consequências

**Ganhos**
- Jogo na nuvem continua instalável pelo Switch, sem ocupar disco.
- A loja não sabe que existe nuvem — nenhuma mudança no Ownfoil.
- Verificado de ponta a ponta: upload com subpastas → origem removida sem sobra →
  o container lê os arquivos pelo mount.

**Custos / riscos**
- O **PC precisa estar ligado** para o Switch baixar da nuvem (é a ponte).
- A instalação a partir da nuvem é limitada pela banda de *download* do PC.
- O scan do Ownfoil lê header de cada NSP/NSZ; sem o cache VFS
  (`--vfs-cache-mode full`) ele rebaixaria da nuvem a cada varredura.
- `rclone mount` morto deixa a loja sem a pasta até reiniciar o container
  (`rprivate`); o supervisor do Ownfoil reconcilia nas varreduras.

## Nota de honestidade
A primeira versão da unit tinha `-o context=system_u:object_r:container_file_t:s0`
e um teste afirmando isso. Medição: o **rclone descarta** o flag (não aparece em
`mount`), o mount fica `fusefs_t`, e funciona porque a política do Fedora deixa
`container_t` ler `fusefs_t` (zero negações AVC, SELinux `Enforcing`). O flag e o
teste foram removidos; hoje o teste **proíbe** o flag e prende o mecanismo real.
