"""Interface MCP remota do Atlas (ADR-0053).

Expõe o Atlas como servidor **MCP (Streamable HTTP)** com **OAuth 2.1**, para o app
do Claude adicionar como conector e acionar o Atlas por chat. Roda como processo
separado (``python -m atlas.mcp``), compartilhando o SQLite do Atlas (WAL). As
ferramentas ficam em ``tools.py`` (puras); o servidor em ``server.py``.
"""
