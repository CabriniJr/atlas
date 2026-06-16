---
titulo: Princípios de produto e engenharia
id: VIS-PRINCIPIOS
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Princípios de produto e engenharia

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

Estes princípios governam todas as decisões. **Quando houver dúvida, eles
decidem.** Um ADR só pode contrariar um princípio se justificar explicitamente.

## P1 — Economia do recurso escasso da assinatura
A IA roda na assinatura Claude (Pro/Max), não por API. O recurso escasso não é o
token em si — é o **limite de uso/sessão da assinatura**. "Economia de token" é o
proxy operacional disso. A maioria das interações deve custar **zero IA**; o
modelo só é invocado quando há análise ou geração genuína a fazer.
→ Ver [ADR-0001](../arquitetura/adr/ADR-0001-ia-em-dois-modos.md).

## P2 — Script-primeiro, agente só quando precisa
Toda rotina faz o trabalho determinístico em código (coletar, comparar, formatar)
e só sobe IA na fase de análise — e somente se um gate justificar.

## P3 — Agnóstico e plugável
O motor não sabe o que é "academia" ou "Librera". Ele só executa o ciclo de vida
de uma rotina. Todo domínio é uma rotina. Domínio nunca vira código do core.

## P4 — O repositório é o estado do sistema
Rotinas são pastas versionadas em git. Adicionar uma rotina = adicionar uma pasta.
Não há painel de configuração. O que o sistema é capaz de fazer está no repo; o
que ele sabe está no banco.

## P5 — Dois modos que nunca se misturam
*Operação* (bot leve no dia a dia) e *desenvolvimento* (gerar rotinas via Claude
Code) são sessões separadas. Quando se tocam (meta-loop), comunicam-se por
**arquivo**, não por estado de runtime.
→ Ver [ADR-0009](../arquitetura/adr/ADR-0009-handoff-entre-modos.md).

## P6 — Interface desacoplada
O canal é um adapter substituível. Telegram hoje; trocar/adicionar é implementar
`enviar` e `receber`. O núcleo não muda.

## P7 — Simplicidade sobre completude
Preferir o caminho mais simples que funciona no notebook de um usuário só, não a
solução "enterprise". YAGNI ruthlessly.

## P8 — A documentação é a fonte de verdade
Código que diverge da doc está errado, ou precisa de um ADR. Toda decisão de
arquitetura vira ADR antes de virar código. Doc desatualizada é bug.

## P9 — Toda decisão é rastreável e reversível
Mudanças entram por commit; decisões entram por ADR. Nada é apagado: documento
superado vira `obsoleto` com link para o sucessor. O meta-loop escreve código
**inativo por padrão**, revisado por humano antes de ativar.

## P10 — Construído por agentes, curado com rigor
O desenvolvimento é feito por agentes em paralelo (best-of-two) e curado pelo Tech
Lead contra esta documentação. Nenhuma solução entra sem passar pela curadoria e
pelo aceite de alto nível do PO/PM.
→ Ver [`../processos/fluxo-de-desenvolvimento.md`](../processos/fluxo-de-desenvolvimento.md).
