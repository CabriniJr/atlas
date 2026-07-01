"""Motor de tradução de PDFs de alta fidelidade (ADR-0030).

Pipeline em 4 estágios: extrair blocos → traduzir por IA → remontar in-place →
checkpoint. Só o texto muda; imagens/vetores/posições permanecem.
"""
