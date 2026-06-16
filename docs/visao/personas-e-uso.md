---
titulo: Personas e uso
id: VIS-PERSONAS
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Personas e uso

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

## Persona única — o dono

O Atlas é **monousuário por design** ([não-objetivo](visao-produto.md#não-objetivos-o-que-o-atlas-não-é)).
A persona é o próprio dono do sistema:

- **Perfil:** técnico, confortável com Linux, git e linha de comando.
- **Infra:** um notebook Linux sempre ligado (systemd, sem sleep) e assinatura
  Claude (Pro/Max) com login ativo.
- **Motivação:** trackear evolução física, cognitiva, estudos e leitura com
  atrito mínimo, e expandir o sistema sem programar manualmente.
- **Restrição:** não quer pagar por token de API; quer custo previsível dentro da
  assinatura.

## Cenários de uso (jornadas)

### J1 — Registro rápido (Camada 0, zero IA)
> "perna hoje, agachamento 80kg 4x10"

O roteador casa a rotina física por trigger, o `collect` extrai os parâmetros por
micro-sintaxe/regex, persiste, e responde uma linha de confirmação. Nenhuma IA.

### J2 — Consulta de status (Camada 0)
> `/status` · `/uso`

Resposta montada por script a partir do banco. Nenhuma IA.

### J3 — Progresso automático (Camada 0 + gate)
A rotina de leitura (Librera) roda agendada, compara o estado, e só notifica se
houve progresso. Você nem fala com o bot: "+12 páginas em [livro] hoje".

### J4 — Resumo diário (Camada 2a, a âncora)
Fim do dia: o sistema coleta tudo que aconteceu e roda **uma** análise
single-turn (Sonnet) que devolve o que você fez, o que ficou pra trás, um insight
e a prévia de amanhã.

### J5 — Criar uma rotina por conversa (meta-loop)
> "quero uma rotina que toda sexta me lembre de revisar X…"

Você descreve no Telegram (fase de planejamento); o bot esclarece até ter o spec;
ao seu comando, o meta-loop gera a pasta da rotina (inativa) via Claude Code; você
revisa no computador e ativa.

## Implicações de design vindas das personas

- **Segurança assume um usuário só:** o bot só responde ao seu ID no Telegram.
- **Entrada otimizada para mobile:** mensagens curtas, micro-sintaxe, confirmações
  de uma linha.
- **Tolerância a falha do notebook:** schedules perdidos (notebook fechado) têm
  catch-up — ver [ciclo de vida](../arquitetura/ciclo-de-vida-rotina.md) e
  [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md).
