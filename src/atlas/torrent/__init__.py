"""Download de torrents headless + verificação de segurança (ADR-0049).

Kind ``Torrent``: recebe um ``.torrent`` (pelo Telegram ou CLI), **verifica** os
metadados (``scan``), **pergunta** ao dono e, confirmado, **baixa** headless via
``qbittorrent-nox`` (``download``), notificando ao terminar. Zero IA — é script
puro (P: economia do recurso escasso).
"""
