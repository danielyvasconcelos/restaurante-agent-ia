# CONCEITOS.md

Guia de estudo do projeto restaurante-agent-ia. Cada entrada traz o conceito, onde ele aparece no código e uma pergunta de entrevista.

## Índice

- [Fundamentos de LLM](#fundamentos-de-llm)
- [RAG](#rag)
- [Agentes e ferramentas](#agentes-e-ferramentas)
- [Avaliação](#avaliação)
- [Engenharia/Infra](#engenhariainfra)
  - [Variáveis de ambiente e segredos](#variáveis-de-ambiente-e-segredos)
  - [Commits semânticos (Conventional Commits)](#commits-semânticos-conventional-commits)
- [Dúvidas para revisar](#dúvidas-para-revisar)

---

## Fundamentos de LLM

_Ainda sem entradas. Começam na Etapa 1 (tokens, temperatura, janela de contexto, prompt de sistema)._

## RAG

_Ainda sem entradas. Começam na Etapa 3 (embeddings, similaridade de cosseno, top-k)._

## Agentes e ferramentas

_Ainda sem entradas. Começam na Etapa 6 (function calling, guardrail)._

## Avaliação

_Ainda sem entradas. Começam na Etapa 12._

## Engenharia/Infra

### Variáveis de ambiente e segredos
- **O que é:** uma variável de ambiente é um valor que fica fora do código e é lido pelo programa quando ele roda. Segredos, como chaves de API, são o uso mais comum. Em desenvolvimento, um arquivo `.env` guarda esses valores localmente.
- **Analogia:** é como a chave de casa no seu bolso, e não colada na porta. A planta da casa (o código) pode ser mostrada a qualquer pessoa sem entregar a chave.
- **Onde aparece no projeto:** `.env.example` (modelo, vai para o Git), `.env` (valores reais, ignorado pelo `.gitignore`) e, a partir da Etapa 1, `app/config.py`, que lê `GEMINI_API_KEY`.
- **Por que usamos:** o código não muda entre máquinas e a chave nunca entra no histórico do Git. A alternativa seria colocar a chave no código, o que a expõe a qualquer pessoa com acesso ao repositório.
- **Pergunta de entrevista:** "Por que não colocar a chave de API no código?" Resposta modelo: porque o código é versionado e compartilhado, e uma chave no histórico do Git continua lá mesmo após apagar o arquivo. Por isso a chave vai em variável de ambiente, e, se vazar, é revogada e substituída.
- **Para estudar mais:** [The Twelve-Factor App: Config](https://12factor.net/pt_br/config) e [Documentação da chave de API do Gemini](https://ai.google.dev/gemini-api/docs/api-key).

### Commits semânticos (Conventional Commits)
- **O que é:** um padrão para escrever mensagens de commit no formato `tipo(escopo): descrição`, como `feat(rag): add semantic search`. O tipo diz que natureza tem a mudança (`feat`, `fix`, `docs`, `chore`, `test`, `build`).
- **Analogia:** é a etiqueta numa caixa de mudança. Sem ler o conteúdo, você já sabe o que tem dentro.
- **Onde aparece no projeto:** em todo commit, um por etapa concluída, na branch `develop`.
- **Por que usamos:** o histórico vira um registro legível do progresso e permite gerar changelog automaticamente. A alternativa, mensagens livres como "ajustes", não diz nada depois de algumas semanas.
- **Pergunta de entrevista:** "Qual a diferença entre `feat` e `chore`?" Resposta modelo: `feat` adiciona funcionalidade visível ao usuário ou à API; `chore` é manutenção que não altera comportamento, como configuração e dependências.
- **Para estudar mais:** [Conventional Commits 1.0.0 (pt-br)](https://www.conventionalcommits.org/pt-br/v1.0.0/).

---

## Dúvidas para revisar

_Nenhuma por enquanto._
