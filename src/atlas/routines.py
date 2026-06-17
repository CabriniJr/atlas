"""Carregador de rotinas do Atlas (E1-01).

Descobre, valida e expõe as rotinas declaradas em ``routines/<nome>/routine.toml``.

Formato de config: **TOML** via ``tomllib`` da stdlib (Python 3.11+).
Motivação: zero dependências externas, tipagem nativa (bool, int, lista),
legível por humanos, read-only — alinhado com o princípio P7 (simplicidade).

Curadoria best-of-two (E1-01): base de implementação simples + mensagens de erro
claras e suíte de testes robusta. Pasta sem ``routine.toml`` é ignorada (não é
rotina); falhas de validação são coletadas sem derrubar as demais (ADR-0006).
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)

# Modelos permitidos para a fase de análise (ver ciclo-de-vida-rotina.md / ADR-0001).
_MODELOS_VALIDOS = {"none", "haiku", "sonnet", "opus"}


@dataclass
class Rotina:
    """Representa uma rotina carregada e validada."""

    # Obrigatórios
    nome: str
    descricao: str

    # Opcionais com default
    triggers: list[str] = field(default_factory=list)
    agenda: str | None = None
    modelo: str = "none"
    gate: str | None = None
    timeout: int | None = None
    budget_tokens: int | None = None
    catch_up: bool = False
    store: str | None = None
    saida: str | None = None
    ativa: bool = True
    label: str | None = None   # grupo de recursos para coletar-por-label
    coletar: str | None = None  # nome do collect no registry; default = nome da rotina

    # Presença de arquivos opcionais na pasta
    tem_collect: bool = False
    tem_prompt: bool = False


@dataclass
class ErroRotina:
    """Registra uma rotina que falhou no carregamento (ADR-0006).

    ``pasta`` é o nome da pasta da rotina; ``mensagem`` aponta o campo/valor.
    """

    pasta: str
    mensagem: str


@dataclass
class ResultadoCarga:
    """Resultado completo da varredura de ``routines/``."""

    rotinas: list[Rotina]
    erros: list[ErroRotina]

    @property
    def ativas(self) -> list[Rotina]:
        """Rotinas com ``ativa=True``."""
        return [r for r in self.rotinas if r.ativa]

    @property
    def inativas(self) -> list[Rotina]:
        """Rotinas com ``ativa=False``."""
        return [r for r in self.rotinas if not r.ativa]


def carregar_rotinas(diretorio: Path) -> ResultadoCarga:
    """Varre *diretorio* e carrega todas as rotinas encontradas.

    Cada subpasta com ``routine.toml`` é uma rotina. Subpastas sem esse arquivo
    são ignoradas (não são rotinas). Falhas de parse ou validação são registradas
    em ``ResultadoCarga.erros`` sem interromper o carregamento das demais
    (ADR-0006).

    Args:
        diretorio: caminho para a pasta ``routines/`` (pode não existir).

    Returns:
        :class:`ResultadoCarga` com as rotinas válidas e os erros.
    """
    if not diretorio.exists():
        return ResultadoCarga(rotinas=[], erros=[])

    rotinas: list[Rotina] = []
    erros: list[ErroRotina] = []

    for entrada in sorted(diretorio.iterdir()):
        if not entrada.is_dir():
            continue  # arquivo solto na raiz: não é rotina
        toml_path = entrada / "routine.toml"
        if not toml_path.exists():
            continue  # pasta sem config: não é uma rotina
        try:
            rotinas.append(_carregar_uma(entrada, toml_path))
        except Exception as exc:  # noqa: BLE001 — resiliência: nada derruba a carga
            _log.warning("Rotina %s ignorada: %s", entrada.name, exc)
            erros.append(ErroRotina(pasta=entrada.name, mensagem=str(exc)))

    return ResultadoCarga(rotinas=rotinas, erros=erros)


def _carregar_uma(pasta: Path, toml_path: Path) -> Rotina:
    """Lê, valida e constrói uma :class:`Rotina` a partir de *toml_path*.

    Raises:
        ValueError: campo obrigatório ausente ou valor fora do domínio.
        tomllib.TOMLDecodeError: TOML malformado.
    """
    with toml_path.open("rb") as fh:
        dados = tomllib.load(fh)

    nome = dados.get("nome")
    descricao = dados.get("descricao")
    if not nome:
        raise ValueError("campo obrigatório 'nome' ausente ou vazio")
    if not descricao:
        raise ValueError("campo obrigatório 'descricao' ausente ou vazio")

    modelo = dados.get("modelo", "none")
    if modelo not in _MODELOS_VALIDOS:
        raise ValueError(
            f"campo 'modelo' inválido: '{modelo}'; esperado um de {sorted(_MODELOS_VALIDOS)}"
        )

    return Rotina(
        nome=nome,
        descricao=descricao,
        triggers=dados.get("triggers", []),
        agenda=dados.get("agenda"),
        modelo=modelo,
        gate=dados.get("gate"),
        timeout=dados.get("timeout"),
        budget_tokens=dados.get("budget_tokens"),
        catch_up=dados.get("catch_up", False),
        store=dados.get("store"),
        saida=dados.get("saida"),
        ativa=dados.get("ativa", True),
        label=dados.get("label"),
        coletar=dados.get("coletar"),
        tem_collect=any(pasta.glob("collect.*")),
        tem_prompt=any(pasta.glob("prompt.*")),
    )
