"""Verificação de integridade pós-download por *magic header* (ADR-0049).

O torrent baixa bit-a-bit conferido (hash por peça), então um download completo
**é** idêntico ao que o `.torrent` descreve. O que o hash NÃO pega é conteúdo
**fake/corrompido na fonte**: um `.nsz`/`.nsp` que não começa com ``PFS0`` dá o
erro "invalid pfs0" ao abrir. Aqui, ao terminar, validamos o magic de cada
arquivo de tipo conhecido; se não bate, avisamos (não apagamos — ADR-0049).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ext → lista de (offset, magic esperado). Basta um bater. Tipos desconhecidos
# são pulados (não reprovam). Switch: NSP e NSZ são contêineres PFS0; XCI é HFS0
# com "HEAD" em 0x100.
_MAGIC: dict[str, list[tuple[int, bytes]]] = {
    ".nsp": [(0, b"PFS0")],
    ".nsz": [(0, b"PFS0")],
    ".xci": [(0x100, b"HEAD")],
    ".xcz": [(0x100, b"HEAD")],
    ".zip": [(0, b"PK\x03\x04"), (0, b"PK\x05\x06"), (0, b"PK\x07\x08")],
    ".pdf": [(0, b"%PDF")],
    ".7z": [(0, b"7z\xbc\xaf\x27\x1c")],
    ".rar": [(0, b"Rar!\x1a\x07")],
    ".gz": [(0, b"\x1f\x8b")],
    ".tgz": [(0, b"\x1f\x8b")],
    ".xz": [(0, b"\xfd7zXZ\x00")],
    ".iso": [(0x8001, b"CD001"), (0x8801, b"CD001"), (0x9001, b"CD001")],
    ".png": [(0, b"\x89PNG\r\n\x1a\n")],
    ".mp4": [(4, b"ftyp")],
    ".mkv": [(0, b"\x1a\x45\xdf\xa3")],
}


@dataclass
class ResultadoIntegridade:
    ok: bool
    verificados: int = 0
    pulados: int = 0
    falhas: list[str] = field(default_factory=list)  # "arquivo: esperado PFS0"

    def humano(self) -> str:
        if self.verificados == 0 and not self.falhas:
            return "integridade: — (nenhum tipo conhecido p/ checar)"
        if self.ok:
            return f"integridade: ✅ ok ({self.verificados} arquivo(s) checado(s))"
        linhas = ["integridade: ⚠️ FALHOU (invalid pfs0 / corrompido)"]
        for f in self.falhas[:6]:
            linhas.append(f"  • {f}")
        return "\n".join(linhas)


def _magic_bate(caminho: str, checagens: list[tuple[int, bytes]]) -> bool:
    try:
        with open(caminho, "rb") as fh:
            for offset, magic in checagens:
                fh.seek(offset)
                if fh.read(len(magic)) == magic:
                    return True
    except OSError:
        return False
    return False


def verificar_arquivo(caminho: str) -> tuple[bool | None, str]:
    """Verifica um arquivo. Devolve ``(ok, detalhe)``; ``ok=None`` = tipo
    desconhecido (pulado)."""
    ext = os.path.splitext(caminho)[1].lower()
    checagens = _MAGIC.get(ext)
    if checagens is None:
        return None, ""
    if _magic_bate(caminho, checagens):
        return True, ""
    esperado = checagens[0][1]
    try:
        legivel = esperado.decode("ascii")
    except UnicodeDecodeError:
        legivel = esperado.hex()
    return False, f"{os.path.basename(caminho)}: esperado magic {legivel!r}"


def verificar(alvo: str) -> ResultadoIntegridade:
    """Verifica um arquivo ou (recursivamente) todos os arquivos de uma pasta."""
    r = ResultadoIntegridade(ok=True)
    caminhos: list[str] = []
    if os.path.isdir(alvo):
        for raiz, _dirs, arqs in os.walk(alvo):
            for a in arqs:
                caminhos.append(os.path.join(raiz, a))
    elif os.path.isfile(alvo):
        caminhos.append(alvo)

    for c in caminhos:
        # ignora arquivos de trabalho do qBittorrent (parciais/incompletos)
        if c.endswith((".!qB", ".parts")) or "/.incompleto/" in c:
            continue
        ok, detalhe = verificar_arquivo(c)
        if ok is None:
            r.pulados += 1
        elif ok:
            r.verificados += 1
        else:
            r.verificados += 1
            r.ok = False
            r.falhas.append(detalhe)
    return r
