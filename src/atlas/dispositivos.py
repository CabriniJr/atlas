"""Auth por dispositivo na Tailnet, com pareamento via Telegram (ADR-0054).

O dashboard do Atlas fica acessível **só pela Tailnet** (não vai pro Funnel) e,
além disso, só para **dispositivos pareados**. O identificador estável de cada
aparelho é o **IP Tailscale** (100.64.0.0/10 v4 ou fd7a:115c:a1e0::/48 v6) — o que
o ``api.py`` enxerga em ``client_address`` quando o aparelho acessa direto pela
tailnet (por isso NÃO usamos ``tailscale serve`` no dash, que esconderia o IP).

Kind ``Dispositivo`` (P11): um recurso por aparelho autorizado (``spec.ip`` +
``spec.nome``). Registro por **pareamento**: o dash mostra um código a um aparelho
não-autorizado; o dono confirma no Telegram (``/autorizar <código>``) e o IP é
salvo. Teto de 3 dispositivos. Zero IA.
"""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass, field
from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

KIND = "Dispositivo"
MAX_DISPOSITIVOS = 3
TTL_PAREAMENTO_S = 300

# Faixas de endereço da Tailscale: CGNAT (v4) e ULA própria (v6).
_TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")
_TAILNET_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


class LimiteDispositivos(Exception):
    """Tentativa de registrar além do teto de ``MAX_DISPOSITIVOS``."""


def _norm_ip(ip: str) -> str | None:
    """Normaliza (desfaz ``::ffff:`` v4-mapeada). ``None`` se não for IP válido."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return str(addr)


def ip_tailnet(ip: str) -> bool:
    """``True`` se o IP pertence à faixa da Tailscale (v4 CGNAT ou v6 ULA)."""
    norm = _norm_ip(ip)
    if norm is None:
        return False
    addr = ipaddress.ip_address(norm)
    return addr in _TAILNET_V4 or addr in _TAILNET_V6


def _nome_recurso(ip: str) -> str:
    """Nome do recurso a partir do IP (estável, único, sem caracteres problemáticos)."""
    return "ip-" + ip.replace(".", "-").replace(":", "_")


@dataclass
class RegistroDispositivos:
    """Registro de dispositivos autorizados + pareamentos pendentes (em memória)."""

    store: ResourceStore
    ttl_pareamento_s: int = TTL_PAREAMENTO_S
    max_dispositivos: int = MAX_DISPOSITIVOS
    # código -> (ip_normalizado, timestamp_de_expiração)
    _pendentes: dict[str, tuple[str, float]] = field(default_factory=dict)

    # -- consulta ----------------------------------------------------------

    def autorizado(self, ip: str) -> bool:
        norm = _norm_ip(ip)
        if norm is None:
            return False
        return self.store.get(KIND, _nome_recurso(norm)) is not None

    def listar(self) -> list[Resource]:
        return self.store.list(KIND)

    # -- pareamento --------------------------------------------------------

    def gerar_codigo(self, ip: str, agora: datetime) -> str:
        """Gera um código de 6 dígitos que vincula ``ip`` por ``ttl`` segundos."""
        norm = _norm_ip(ip) or ip
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        self._pendentes[codigo] = (norm, agora.timestamp() + self.ttl_pareamento_s)
        return codigo

    def confirmar(
        self, codigo: str, agora: datetime, nome: str | None = None
    ) -> Resource | None:
        """Valida o código (uso único, respeitando TTL) e registra o dispositivo.

        Levanta ``LimiteDispositivos`` se já há ``max`` aparelhos e este é novo.
        ``None`` se o código é inválido/expirado.
        """
        entrada = self._pendentes.pop(codigo, None)
        if entrada is None:
            return None
        ip, expira_em = entrada
        if agora.timestamp() > expira_em:
            return None
        return self._registrar(ip, nome, agora)

    def _registrar(self, ip: str, nome: str | None, agora: datetime) -> Resource:
        nome_rec = _nome_recurso(ip)
        ja_existe = self.store.get(KIND, nome_rec) is not None
        if not ja_existe and len(self.listar()) >= self.max_dispositivos:
            raise LimiteDispositivos(
                f"limite de {self.max_dispositivos} dispositivos atingido"
            )
        res = Resource(
            kind=KIND,
            name=nome_rec,
            labels={"tipo": "dispositivo"},
            spec={"ip": ip, "nome": nome or ip},
        )
        return self.store.apply(res, agora)

    def revogar(self, ip: str, agora: datetime) -> bool:
        norm = _norm_ip(ip) or ip
        return self.store.delete(KIND, _nome_recurso(norm))


# -- singleton compartilhado (api.py gera o código; Telegram confirma) ---------
# Os pareamentos pendentes vivem em memória, então os dois lados PRECISAM da mesma
# instância — daí o singleton de processo, semeado no boot.
_REGISTRO: RegistroDispositivos | None = None


def init_registro(store: ResourceStore) -> RegistroDispositivos:
    global _REGISTRO
    _REGISTRO = RegistroDispositivos(store)
    return _REGISTRO


def registro() -> RegistroDispositivos | None:
    return _REGISTRO


# -- comandos do Telegram ------------------------------------------------------


def responder_comando(texto: str, agora: datetime) -> str | None:
    """Handler de ``/autorizar``, ``/dispositivos`` e ``/revogar``. ``None`` se o
    texto não é um desses comandos (deixa o roteador seguir)."""
    t = texto.strip()
    cmd = t.split()[0] if t else ""
    if cmd not in ("/autorizar", "/dispositivos", "/revogar"):
        return None
    reg = registro()
    if reg is None:
        return "⚠️ registro de dispositivos indisponível (API não iniciada)."

    if cmd == "/dispositivos":
        ds = reg.listar()
        if not ds:
            return "📱 Nenhum dispositivo autorizado ainda."
        linhas = [
            f"• {d.spec.get('nome', d.spec.get('ip'))} — `{d.spec.get('ip')}`" for d in ds
        ]
        return f"📱 Dispositivos autorizados ({len(ds)}/{reg.max_dispositivos}):\n" + "\n".join(
            linhas
        )

    if cmd == "/revogar":
        partes = t.split(maxsplit=1)
        if len(partes) < 2:
            return "uso: /revogar <ip ou nome>"
        alvo = partes[1].strip()
        # aceita por IP direto ou por nome (procura o IP correspondente)
        ip = alvo
        if _norm_ip(alvo) is None:
            achado = next(
                (d.spec.get("ip") for d in reg.listar() if d.spec.get("nome") == alvo), None
            )
            ip = achado or alvo
        return f"🗑️ dispositivo revogado: {alvo}" if reg.revogar(ip, agora) else (
            f"não encontrei dispositivo: {alvo}"
        )

    # /autorizar <codigo> [nome]
    partes = t.split(maxsplit=2)
    if len(partes) < 2:
        return "uso: /autorizar <código> [nome]"
    codigo = partes[1].strip()
    nome = partes[2].strip() if len(partes) > 2 else None
    try:
        d = reg.confirmar(codigo, agora, nome=nome)
    except LimiteDispositivos:
        return (
            f"⚠️ limite de {reg.max_dispositivos} dispositivos atingido. "
            "Revogue um com /revogar antes."
        )
    if d is None:
        return "❌ código inválido ou expirou. Recarregue a página e tente de novo."
    return f"✅ dispositivo autorizado: {d.spec.get('nome')} (`{d.spec.get('ip')}`)"
