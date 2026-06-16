---
titulo: Visão de produto
id: VIS-PRODUTO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Visão de produto

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

## North star

Um **assistente pessoal que se expande sozinho**: roda no notebook sempre ligado,
usa o Claude como motor de inteligência, fala pelo Telegram, e cria as próprias
rotinas a partir de conversa. O valor não está em trackear — está no **meta-loop**
que faz o sistema crescer com você, de forma rastreável e barata.

## O problema

Ferramentas de tracking pessoal exigem disciplina de entrada (apps, formulários,
planilhas), são fechadas (você não estende o que elas fazem) e, quando usam IA,
custam caro por interação. Resultado: ou você abandona, ou paga demais, ou fica
preso ao que o app decidiu oferecer.

## Dores que o Atlas resolve

| Dor | Como o Atlas ataca |
|---|---|
| **Entrada de dados é trabalhosa** | Mensagem curta no Telegram; o resto é script. |
| **IA é cara para uso contínuo** | ~80% das interações custam zero IA (Camada 0). |
| **Ferramentas são fechadas** | Toda capacidade é uma rotina plugável; você cria novas por conversa. |
| **Configurar é complicado** | Não há painel: adicionar rotina = adicionar pasta versionada. |
| **Falta visão de progresso** | Metas como camada transversal + resumo diário com insight. |
| **Lock-in de fornecedor** | Interface e motor são adapters substituíveis. |

## Para quem é (resumo — ver [personas](personas-e-uso.md))

Um usuário único, técnico, com um notebook Linux sempre ligado e assinatura
Claude (Pro/Max). Quer trackear evolução física, cognitiva, estudos e leitura, e
quer poder **expandir o sistema sem programar manualmente**.

## Não-objetivos (o que o Atlas **não** é)

- **Não é multiusuário.** É de uma pessoa só; segurança assume isso.
- **Não é um SaaS.** Roda local; sem domínio, sem conta na nuvem obrigatória.
- **Não é um chatbot genérico.** A IA é reservada a análise e geração, não a
  conversa fiada.
- **Não busca completude enterprise.** Simplicidade que funciona no notebook de
  uma pessoa vence a solução "robusta" genérica.

## Como saberemos que deu certo (sinais)

- A maioria das interações diárias resolve sem IA.
- Adicionar uma rotina nova é uma conversa + uma revisão, não um projeto.
- O custo de IA fica dentro do orçamento da assinatura, observável via `/uso`.
- O resumo diário é útil o bastante para você esperar por ele.

## Documentos relacionados

- Princípios que governam as decisões: [`principios.md`](principios.md)
- Como isso vira arquitetura: [`../arquitetura/visao-geral.md`](../arquitetura/visao-geral.md)
- O que vamos construir primeiro: [`../roadmap/amadurecimento.md`](../roadmap/amadurecimento.md)
