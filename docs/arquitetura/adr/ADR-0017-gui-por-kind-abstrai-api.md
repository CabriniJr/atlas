---
titulo: ADR-0017 — Todo Kind tem interação GUI completa que abstrai a API
id: ADR-0017
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
substitui: —
substituido-por: —
---

# ADR-0017 — Todo Kind tem interação GUI completa que abstrai a API

## Histórico de revisão
| Versão | Data       | Autor     | Mudança  | Aprovado por |
|--------|------------|-----------|----------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Proposta + aceite | PO/PM |

---

## Status
`aceito`.

## Contexto

O Atlas tem três frentes sobre o mesmo contrato ([ADR-0015](ADR-0015-core-api-de-objetos.md)):
`atlasctl` (CLI), Telegram (`atlascli`) e o dashboard web (`builder` gráfico).
Até aqui, a GUI cobria bem **leitura** e **edição de manifesto**, mas as **ações**
e a **configuração assistida** de cada Kind ainda exigiam digitar comandos
(ex.: iniciar um Timer, registrar um valor de Tracker, recalcular um Goal).

O PO definiu a diretriz: *"todo kind precisa ter uma interação GUI fácil e
completa, e essa interação é simplesmente uma abstração da API"* — espelhando as
janelas de configuração de um alarme ou evento de calendário, com ações diretas
(start/stop de Timer) acessíveis na tela inicial e no graph.

## Decisão

A GUI do dashboard é uma **abstração fiel da API de objetos** — nunca um caminho
paralelo. Para **todo Kind** valem três camadas:

1. **Configuração assistida (form tipado).** Criar/editar um recurso usa controles
   visuais conforme o `_KIND_SCHEMA` (toggle para bool, botões para enum, número,
   texto/área), tanto no painel do graph quanto no editor de manifesto. Campos
   fora do schema continuam como pares chave-valor livres. Equivalente às "janelas"
   de configurar alarme/evento.

2. **Ações por Kind.** Cada Kind expõe suas ações de domínio como botões que
   **apenas traduzem para chamadas da API** (`POST /_cmd`, `/_run`, `PUT`):
   - `Timer` → ▶ Iniciar / ⏹ Parar (`/timer start|finish`)
   - `Tracker` → 📝 registrar valor (micro-sintaxe `<syntax> <valor>`)
   - `Routine` → ▶ Executar (`/_run`) · 📝 Check-in quando coleta um grupo
   - `Goal` → 🎯 Recalcular (`/goal check`)
   - `Repo` → 🧠 Insight (IA)
   As ações aparecem na **card** (explorer), na tela **inicial** (status) e no
   **graph**.

3. **Entrada de valores visual.** Coletas que pedem valores (ex.: trackers de um
   grupo) têm formulário no web — uma caixa por item, derivada da rotina/grupo
   configurado — além do fluxo por Telegram.

Regras invioláveis:
- **Zero lógica de negócio no front.** O front monta o comando; o backend decide.
  Toda ação é um verbo/endpoint já existente da API.
- **Adicionar um Kind = registrar schema + ações.** Sem isso, o Kind ainda
  funciona (form genérico de manifesto), mas não cumpre a diretriz.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Só editor de manifesto (JSON/KV) | simples | exige o usuário saber o schema; sem ações | não é "fácil e completa" |
| Dialogs hard-coded por Kind no front | controle fino | duplica regras; front vira fonte de verdade | viola "abstração da API" |
| Schema declarativo + ações que chamam a API | reuso; front fino; 1 fonte de verdade | exige manter o schema | escolhido |

## Consequências
- **Positivas:** paridade CLI/Telegram/web; curva de uso baixa; o front nunca
  diverge do backend (só chama a API); novos Kinds ganham GUI declarando schema+ações.
- **Negativas / custos:** manter `_KIND_SCHEMA` e o mapa de ações em dia com os Kinds;
  o `/_cmd` do web passa pelo handler completo (mesmo motor do Telegram).
- **Impacto na constituição:** reforça "o repositório é o estado" e "agnóstico e
  plugável"; nenhuma decisão anterior muda.

## Pendências
- **Janelas mexíveis** na tela inicial (widgets reordenáveis/arrastáveis) — a fazer.
- Dialogs ainda mais ricos por Kind (ex.: seletor de horário do Alarm, cron-builder
  visual da Routine) — incremental sobre o form tipado.
- Cobrir todos os Kinds com ações (Alarm enable/disable, Doc export, etc.).
- Insights de IA são arquivados como `Doc` na "pasta" do repositório
  (`labels: topic=repo, repo=<nome>, tipo=insight`) — ver [ADR-0016](ADR-0016-ia-plugavel-kind-prompt.md).
