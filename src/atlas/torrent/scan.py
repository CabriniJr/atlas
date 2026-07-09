"""Varredura de segurança de arquivos ``.torrent`` — só metadados (ADR-0049).

Portado do ``~/bin/torrent-scan.py`` do PO para dentro do repo (P4: o repositório
é o estado do sistema), como funções importáveis e testáveis. Um ``.torrent`` não
carrega o conteúdo, só metadados; inspecioná-los levanta sinais de risco ANTES de
baixar. Bencode em stdlib pura, sem dependências.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Bencode (formato dos .torrent), stdlib pura.
# ---------------------------------------------------------------------------


def bdecode(data: bytes):
    """Decodifica bencode. Levanta ``ValueError`` em entrada malformada."""

    def parse(i: int):
        c = data[i : i + 1]
        if c == b"i":
            end = data.index(b"e", i)
            return int(data[i + 1 : end]), end + 1
        if c.isdigit():
            colon = data.index(b":", i)
            length = int(data[i:colon])
            start = colon + 1
            return data[start : start + length], start + length
        if c == b"l":
            i += 1
            out = []
            while data[i : i + 1] != b"e":
                val, i = parse(i)
                out.append(val)
            return out, i + 1
        if c == b"d":
            i += 1
            out = {}
            while data[i : i + 1] != b"e":
                key, i = parse(i)
                val, i = parse(i)
                out[key] = val
            return out, i + 1
        raise ValueError(f"bencode inválido na posição {i}")

    value, _ = parse(0)
    return value


def bencode(obj) -> bytes:
    if isinstance(obj, int):
        return b"i" + str(obj).encode() + b"e"
    if isinstance(obj, bytes):
        return str(len(obj)).encode() + b":" + obj
    if isinstance(obj, str):
        b = obj.encode()
        return str(len(b)).encode() + b":" + b
    if isinstance(obj, list):
        return b"l" + b"".join(bencode(x) for x in obj) + b"e"
    if isinstance(obj, dict):
        items = sorted(obj.items())
        return b"d" + b"".join(bencode(k) + bencode(v) for k, v in items) + b"e"
    raise TypeError(f"tipo não suportado: {type(obj)}")


# ---------------------------------------------------------------------------
# Regras de risco.
# ---------------------------------------------------------------------------

EXT_PERIGOSAS = {
    ".exe", ".scr", ".com", ".pif", ".bat", ".cmd", ".msi", ".msp",
    ".js", ".jse", ".vbs", ".vbe", ".wsf", ".wsh", ".ps1", ".psm1",
    ".jar", ".lnk", ".reg", ".hta", ".cpl", ".dll", ".sys", ".apk",
    ".sh", ".run", ".bin", ".deb", ".rpm", ".appimage", ".dmg", ".pkg",
}
EXT_ARQUIVO = {".zip", ".rar", ".7z", ".iso", ".gz", ".tar", ".tgz", ".cab"}
EXT_MIDIA = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mpg", ".mpeg",
    ".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac",
    ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".epub", ".txt", ".doc", ".docx",
    ".nsp", ".xci", ".img", ".xz",
}
NOMES_SUSPEITOS = {"autorun.inf", "desktop.ini", "thumbs.db"}
EXT_SUSPEITA_NOME = {".url", ".lnk", ".website"}


@dataclass
class ResultadoScan:
    """Resultado da varredura de um ``.torrent``. ``risco``: 0 ok, 1 aviso, 2 perigo."""

    ok: bool
    risco: int
    nome: str = ""
    infohash: str = ""
    versao: str = ""
    total_bytes: int = 0
    num_arquivos: int = 0
    alertas: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    erro: str = ""

    def humano(self) -> str:
        """Resumo curto p/ o Telegram (multi-linha, texto puro)."""
        if not self.ok:
            return f"❌ não é um .torrent válido: {self.erro}"
        selo = {0: "✅ só mídia/dados", 1: "⚠️ pede atenção", 2: "🚨 PERIGO"}[self.risco]
        linhas = [
            f"📦 {self.nome}",
            f"{selo}  ·  {tamanho_humano(self.total_bytes)}  ·  "
            f"{self.num_arquivos} arquivo(s)  ·  {self.versao}",
        ]
        for a in self.alertas[:6]:
            linhas.append(f"  • {a}")
        for n in self.notas[:4]:
            linhas.append(f"  ℹ {n}")
        return "\n".join(linhas)


def tamanho_humano(n: int) -> str:
    v = float(n)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unidade == "TB":
            return f"{int(v)} B" if unidade == "B" else f"{v:.1f} {unidade}"
        v /= 1024
    return f"{v:.1f} TB"


def _ext(nome: str) -> str:
    return os.path.splitext(nome.lower())[1]


def _coletar_v2(node, prefixo="") -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for chave, val in node.items():
        nome = chave.decode("utf-8", "replace")
        if nome == "" and isinstance(val, dict) and b"length" in val:
            out.append((prefixo.rstrip("/"), val[b"length"]))
        elif isinstance(val, dict):
            out.extend(_coletar_v2(val, prefixo + nome + "/"))
    return out


def _eh_padding(caminho: str) -> bool:
    base = caminho.lower()
    return (
        "_____padding_file" in base
        or base.startswith(".pad/")
        or "/.pad/" in base
        or base.endswith(".pad")
    )


def infohash_de(meta: dict) -> str:
    return hashlib.sha1(bencode(meta[b"info"])).hexdigest()  # noqa: S324 (infohash é SHA-1 por spec)


def analisar_bytes(data: bytes) -> ResultadoScan:
    """Analisa o conteúdo de um ``.torrent`` (bytes). Nunca levanta — devolve
    ``ResultadoScan(ok=False, risco=2, erro=...)`` em entrada inválida."""
    try:
        meta = bdecode(data)
    except Exception as e:  # noqa: BLE001
        return ResultadoScan(ok=False, risco=2, erro=f"não consegui ler como .torrent: {e}")
    if not isinstance(meta, dict) or b"info" not in meta:
        return ResultadoScan(ok=False, risco=2, erro="arquivo não parece um .torrent válido")

    info = meta[b"info"]
    infohash = infohash_de(meta)
    nome = info.get(b"name", b"?").decode("utf-8", "replace")

    tem_v1 = (b"files" in info) or (b"length" in info)
    tem_v2 = info.get(b"meta version") == 2 or b"file tree" in info
    versao = "híbrido (v1+v2)" if (tem_v1 and tem_v2) else ("v2" if tem_v2 else "v1")

    notas: list[str] = []
    if b"comment" in meta:
        com = meta[b"comment"].decode("utf-8", "replace")
        if any(u in com.lower() for u in ("http://", "https://", "www.")):
            notas.append("comentário contém URL (comum em spam/fake)")
    if info.get(b"private") == 1:
        notas.append("torrent PRIVADO: DHT/PeX/LSD desativados; só trackers")

    trackers: list[str] = []
    if b"announce" in meta:
        trackers.append(meta[b"announce"].decode("utf-8", "replace"))
    for tier in meta.get(b"announce-list", []):
        for t in tier:
            trackers.append(t.decode("utf-8", "replace"))
    if not trackers:
        notas.append("sem trackers (só DHT/magnet)")

    arquivos: list[tuple[str, int]] = []
    if b"files" in info:
        for f in info[b"files"]:
            partes = [p.decode("utf-8", "replace") for p in f[b"path"]]
            arquivos.append(("/".join(partes), f[b"length"]))
    elif b"length" in info:
        arquivos.append((nome, info[b"length"]))
    elif b"file tree" in info:
        arquivos = _coletar_v2(info[b"file tree"])

    reais = [(n, t) for n, t in arquivos if not _eh_padding(n)]
    total = sum(t for _, t in reais)

    alertas: list[str] = []
    nivel = 0
    minusculos = 0
    for nome_f, tam in reais:
        base = nome_f.lower()
        e = _ext(base)
        e2 = _ext(os.path.splitext(base)[0])
        if e2 in EXT_MIDIA and e in EXT_PERIGOSAS:
            alertas.append(f"dupla extensão enganosa: {nome_f}")
            nivel = max(nivel, 2)
        elif e in EXT_PERIGOSAS:
            alertas.append(f"executável/script: {nome_f}")
            nivel = max(nivel, 2)
        elif e in EXT_ARQUIVO:
            alertas.append(f"compactado (verifique após extrair): {nome_f}")
            nivel = max(nivel, 1)
        elif e in EXT_SUSPEITA_NOME or os.path.basename(base) in NOMES_SUSPEITOS:
            alertas.append(f"arquivo suspeito: {nome_f}")
            nivel = max(nivel, 1)
        if tam < 10 * 1024:
            minusculos += 1

    if len(reais) > 20 and minusculos > len(reais) * 0.5:
        notas.append(f"{minusculos}/{len(reais)} arquivos < 10 KB (padrão fake/spam)")
    if len(reais) == 1 and _ext(reais[0][0]) in (EXT_PERIGOSAS | EXT_ARQUIVO):
        notas.append("torrent de um único executável/compactado — confira a fonte")

    return ResultadoScan(
        ok=True,
        risco=nivel,
        nome=nome,
        infohash=infohash,
        versao=versao,
        total_bytes=total,
        num_arquivos=len(reais),
        alertas=alertas,
        notas=notas,
    )


def analisar_arquivo(caminho: str) -> ResultadoScan:
    with open(caminho, "rb") as f:
        return analisar_bytes(f.read())
