# Restaurante da Dani: atendente virtual com RAG e function calling

Agente de atendimento para um restaurante fictício. O cliente conversa em português, pergunta sobre pratos, ingredientes e alergênicos, e monta o pedido. O agente responde com base no cardápio, altera a comanda por meio de ferramentas e **nunca adiciona um prato com um alergênico que o cliente declarou**.

> Projeto de portfólio, feito para estudar na prática como construir um agente de LLM que é confiável, medido e barato de operar. Não é um produto: não tem login, pagamento nem deploy.

**Stack:** Python · FastAPI · Google Gemini (`gemini-3.1-flash-lite` e `gemini-embedding-2`) · Pydantic · pytest · HTML/CSS/JS puro · Docker

---

## 1. O problema

Um atendente de restaurante, humano ou automático, recebe perguntas como:

- "O risoto tem glúten?"
- "O que posso comer sem lactose?"
- "Põe duas moquecas de camarão no meu pedido. Ah, tenho alergia a lactose."

Um LLM sozinho falha nisso de três formas, e as três têm custo real:

| Falha | Exemplo | Por que importa |
|---|---|---|
| **Alucinação** | Inventar um prato ou dizer que o pudim não tem lactose | Informação errada sobre alergia pode causar dano à saúde |
| **Não age no mundo** | Dizer "adicionei" sem alterar nenhuma comanda | O pedido nunca é registrado |
| **Não é medido** | Ninguém sabe quanto cada conversa custa nem quanto demora | Não dá para operar nem melhorar |

O problema, portanto, não é "fazer um chatbot responder". É fazer um agente que **responde só com o que está no cardápio, age de forma verificável e tem segurança onde o erro é perigoso**.

---

## 2. A solução

Quatro técnicas, cada uma resolvendo uma das falhas acima.

```
 Cliente ── mensagem ──▶ FastAPI /chat
                            │
        ┌───────────────────┼───────────────────────────────┐
        ▼                   ▼                               ▼
   Busca semântica      Loop do agente               Guardrail em código
   (RAG, top-4 pratos)  (Gemini + 4 ferramentas)     (veta alergênicos)
        │                   │                               │
        └──▶ contexto ──────┤◀──── resultado das ferramentas┘
                            ▼
                    Resposta + estado real da comanda + métricas
```

### 2.1 RAG (Retrieval-Augmented Generation): ancorar o modelo no cardápio

Cada prato vira um **chunk** (1 prato = 1 chunk) com nome, descrição, ingredientes e alergênicos. Os chunks são transformados em **embeddings** (vetores de 768 números). Para cada pergunta, calculamos o embedding dela e buscamos os 4 pratos mais parecidos por **similaridade de cosseno** (vetores normalizados e produto escalar, via NumPy). Esses 4 pratos entram no prompt, e o modelo é instruído a responder só com eles.

*Por que não um banco vetorial?* São 15 pratos. Um arquivo JSON e uma multiplicação de matrizes bastam e deixam o mecanismo visível. Num cardápio de milhares de itens, a decisão mudaria.

### 2.2 Function calling: o modelo decide, o código executa

O modelo recebe quatro ferramentas e decide quando chamá-las:

| Ferramenta | O que faz |
|---|---|
| `adicionar_item` | Põe um prato na comanda |
| `remover_item` | Tira um prato da comanda |
| `ver_carrinho` | Lê a comanda e o total |
| `filtrar_pratos` | Filtra o cardápio de forma determinística (sem alergênico X, categoria, preço máximo) |

O modelo **nunca** altera a comanda diretamente. Ele pede, o nosso código valida e executa, e o resultado volta ao modelo. Erros voltam como dados (`{"ok": false, "erro": "prato_ambiguo"}`) e não como exceções, para o modelo poder se corrigir. O loop tem no máximo 5 passos.

### 2.3 Guardrail de alergênicos: segurança em código, não em prompt

Quando o cliente diz "tenho alergia a lactose", um detector por léxico (regex) registra a restrição na sessão. Se o modelo tentar `adicionar_item` com um prato que contém esse alergênico, **o código recusa**, devolve `alergenico_detectado` e a interface mostra o carimbo "Não adicionado". O modelo não consegue se autoconfirmar: uma confirmação só vale se o alerta estava no turno imediatamente anterior e o cliente confirmou de forma clara.

*Por que em código?* Um prompt é um pedido; um `if` é uma garantia. Para um risco de saúde, usamos a garantia.

### 2.4 Medição e controle de custo

Cada requisição grava em `data/metricas.jsonl`: tokens de entrada e saída, número de chamadas ao modelo, latência (busca, modelo, total) e custo em dólares. Há um teto diário de gasto (`ORCAMENTO_DIARIO_USD`) que responde HTTP 429 quando atingido.

---

## 3. Minha contribuição específica

**Decisões de projeto**

- **Guardrail em código com semântica de confirmação.** O modelo não pode confirmar por conta própria. A confirmação exige alerta no turno anterior e um "sim" explícito do cliente.
- **`filtrar_pratos` como ferramenta determinística**, criada depois de eu observar que o RAG não responde "quais pratos não têm lactose?". Veja a seção 4.
- **Turno atômico.** Antes de cada turno, tiro uma foto do estado da sessão (`checkpoint`). Se o Gemini falha depois de uma ferramenta já ter alterado a comanda, o estado é restaurado e o cliente não fica com um item que não viu ser adicionado. Há também uma trava por sessão para um turno de cada vez.
- **Privacidade nas métricas.** Não guardo o texto das mensagens (podem conter dados de saúde) e o `session_id` entra só como hash.
- **Defesa em camadas contra gasto descontrolado:** mensagem de até 500 caracteres, 5 passos por turno, 50 mensagens por conversa, timeout de 30 s por chamada ao modelo e teto diário de US$ 2.
- **Interface com renderização segura.** A saída do modelo é tratada como entrada não confiável: sem `innerHTML`, com Content-Security-Policy. Testes automáticos falham se alguém introduzir script inline ou recurso externo.
- **Interface honesta.** A comanda mostrada vem do estado do servidor, não do que o modelo escreveu. O painel lista o que o atendente de fato fez e rotula como "Tentou adicionar" quando a ação falha.

**Qualidade**

- 208 testes automatizados (cardápio, RAG, carrinho, ferramentas, loop do agente, guardrail, sessões, API, métricas e interface), rodando sem chamar a API paga.
- **Avaliação com gabarito** (23 casos, verificações de estado e de texto), com repetição de rodadas e separação entre erro do agente e erro do provedor.
- Chave de API apenas em `.env` (ignorado pelo git); commits semânticos por etapa.

---

## 4. As dificuldades

**Dificuldade 1: o RAG não sabe responder "todos os pratos que não têm X".**

A busca semântica devolve os pratos *mais parecidos* com a pergunta. Mas "quais pratos não têm lactose?" pede uma resposta sobre o cardápio *inteiro*, e a negação não é bem capturada por similaridade. O modelo recebia 4 pratos e respondia com base só neles.

*Tentativa descartada:* um limiar de similaridade para filtrar resultados. Medi as pontuações e vi que perguntas relevantes e irrelevantes se **sobrepõem**, então não existe um limiar que separe as duas.

*Solução:* tirar a pergunta do RAG e dar ao modelo a ferramenta `filtrar_pratos`, que consulta o cardápio completo com filtros exatos. O resultado para lactose, verificável na base: Feijoada, Moqueca de Peixe, Moqueca de Camarão, Bowl Vegano e Suco de Laranja.

*Lição:* RAG é para perguntas sobre *um assunto*. Perguntas de *conjunto completo* pedem um filtro exato.

**Dificuldade 2: o modelo "lembrava" de coisas que o cliente não disse.**

Numa conversa real, o modelo escreveu "você mencionou restrições" sem o cliente ter mencionado nada. Prompt pedindo cuidado não bastou. A solução foi registrar as alergias no **código** (estado de sessão) e injetar no prompt só o que foi de fato declarado.

**Dificuldade 3: latência muito variável.**

Nas conversas reais, respostas de 1 s conviveram com uma de 25 s. A média escondia isso, e por isso as métricas reportam **mediana (p50) e p95**, e não só a média. Com poucos dados, a média foi de 6,3 s e o p95 de 20,6 s.

**Dificuldade 4: o custo cresce a cada turno.**

O histórico completo é reenviado ao modelo a cada mensagem, então o custo por turno aumenta ao longo da conversa. Está documentado como limitação, e o limite de 50 mensagens por conversa controla o pior caso.

**Dificuldade 5: o agente respondia assunto fora do restaurante.**

A avaliação achou o que eu não tinha visto: para "Qual é a capital da França?", o atendente respondeu "Paris". O prompt tinha 11 regras sobre cardápio, pedido e alergia e **nenhuma sobre assunto fora do escopo**. O mesmo caso tinha passado na rodada anterior, então o comportamento era instável, não ausente.

*Solução:* uma regra de escopo no prompt (e outra para não revelar as instruções). Para não ajustar só até passar, escrevi dois casos novos *depois* de ver a falha (uma conta e uma pergunta de futebol). Resultado: nenhuma falha em 3 rodadas, e os dois casos novos recusaram corretamente.

*Limite honesto:* é uma regra de prompt, não uma garantia em código. Num conjunto pequeno, "não apareceu falha" não é o mesmo que "nunca falha".

**Dificuldade 6: o provedor falha, e isso não pode virar nota do agente.**

Na primeira avaliação, 2 casos falharam por erro do Google (503 de sobrecarga e 429 de limite por minuto). Contar isso como erro do agente daria "90%", um número que não descreve o agente. O executor agora separa **erro do provedor** de **resposta errada**, calcula o acerto sobre os casos que rodaram e tenta de novo (até 3 vezes, esperando 40 s no 429).

**Bugs encontrados pelos testes (e não por mim)**

- A regex de alergia a amendoim aceitava `amendoins?` e não reconhecia "amendoim". Um teste que percorre todos os alergênicos do enum pegou isso. Corrigido para `\bamendoi(?:m|ns)\b`.
- O preço saía como `49.9` na API. Corrigido com serializador para `"49.90"`.
- No próprio gabarito da avaliação, a expressão que detecta "contém glúten" casava `tem` dentro de `contem`, e reprovaria respostas corretas como "não contém glúten". Corrigido com `\b` e testes de respostas certas e erradas.

---

## 5. Como medimos o resultado

### 5.1 O que já é medido

| O quê | Como | Onde |
|---|---|---|
| Corretude do código | 208 testes automatizados, sem rede | `pytest` |
| Segurança do guardrail | Testes percorrem todos os 9 alergênicos e os cenários de confirmação | `tests/test_guardrails.py` |
| Segurança da interface | Testes de CSP, ausência de `innerHTML` e de recursos externos | `tests/test_frontend.py` |
| Tokens e custo por requisição | Contagem de tokens retornada pelo Gemini × preço por milhão | `app/llm.py`, `data/metricas.jsonl` |
| Latência | Cronometrada separadamente em busca, modelo e total | `app/metrics.py` |
| Resumo | Média, p50, p95, máximo, taxa de sucesso e falhas por status | `python -m scripts.relatorio_metricas` |

Preços usados: US$ 0,25 por milhão de tokens de entrada e US$ 1,50 por milhão de saída (tokens de "pensamento" cobrados como saída).

### 5.2 Avaliação de qualidade das respostas

**Como funciona.** `eval/eval_set.json` tem **23 casos em 6 categorias**, cada um com um gabarito. `python -m eval.run_eval` roda tudo com o Gemini de verdade, em sessões novas, e confere cada caso com verificações determinísticas (sem outro LLM como juiz):

- **de estado** (as mais fortes): quais ferramentas rodaram com sucesso, qual ficou a comanda final, quais alergias foram registradas;
- **de texto** (mais grosseiras): trechos que devem ou não aparecer na resposta, ignorando acento e maiúsculas, com expressão regular para negações como "não contém glúten".

O executor separa **erro do provedor** (429, 5xx, timeout) de **resposta errada**, e tenta de novo até 3 vezes.

**Resultado final** (`gemini-3.1-flash-lite`, 23 casos × 3 rodadas = 69 conversas, em 07/11/2026):

| Categoria | Casos | Aprovados nas 3 rodadas |
|---|---|---|
| Alergênicos de um prato | 4 | 12/12 |
| Preço e ingredientes | 4 | 12/12 |
| Perguntas de conjunto | 4 | 12/12 |
| Montar o pedido | 4 | 12/12 |
| Guardrail de alergia | 3 | 9/9 |
| Fora do escopo e robustez | 4 | 12/12 |
| **Total** | **23** | **69/69** |

| Métrica | Valor |
|---|---|
| Custo total (69 conversas, 78 turnos) | US$ 0,0536 |
| Custo médio por caso / por turno | US$ 0,0008 / US$ 0,0007 |
| Tokens | 177.611 de entrada, 6.145 de saída |
| Latência por turno (média, p50, p95, máx) | 2,83 s, 1,4 s, 7,16 s, 33,18 s |
| Casos que precisaram de nova tentativa (erro do provedor) | 7 de 69 |

O custo é dominado pela **entrada** (cerca de 83%), porque o prompt de sistema e o histórico são reenviados a cada chamada.

**Como o resultado evoluiu** (a avaliação serviu para achar defeitos, não só para dar nota):

| Rodada | O que aconteceu |
|---|---|
| 1 (21 casos) | 19 de 19 dos casos que rodaram; 2 não rodaram por erro do provedor (503 e 429). Latência p50 3,55 s, p95 20,14 s. |
| 2 (21 casos) | 20 de 21. Falha real: o agente respondeu "Paris" a uma pergunta fora do escopo. Latência p50 5,67 s, p95 23,66 s. |
| 3 (23 casos × 3, prompt com regra de escopo) | 69 de 69. Resultado da tabela acima. |

### 5.3 Como interpretar os números

- **São 23 casos distintos, não 69.** Repetir 3 vezes mede **estabilidade**; não mede o quanto o agente acerta perguntas fora do conjunto. Um caso vale cerca de 4,3 pontos percentuais.
- **"69/69" não é garantia.** Com esse tamanho, é um indicador de que o comportamento é consistente nos casos conhecidos. O `limite-01` já tinha passado uma vez antes de falhar, o que mostra que o agente é probabilístico.
- **O guardrail tem duas camadas, e a avaliação exercita só uma.** O veto em código (`alergenico_detectado`) apareceu apenas no caso `guard-02`. No `guard-01` o modelo recusou sozinho, sem chamar a ferramenta. No `guard-03` o pedido foi corretamente aceito (alergia a camarão, prato de peixe), ou seja, sem falso positivo. O veto em código é garantido pelos testes automáticos (`tests/test_guardrails.py`), não por esta avaliação.
- **Parte do conjunto foi escrita depois de ver uma falha** (`limite-03` e `limite-04`). Isso foi proposital, para testar se a correção generaliza, mas esses casos não são "cegos".
- **A latência depende do provedor.** Com o mesmo código, o p50 foi de 5,67 s numa rodada e de 1,4 s em outra. Os números **não incluem tentativas que falharam nem o tempo de espera** entre elas.
- **O custo é o preço de tabela.** Se a chave estiver no plano gratuito (veja as limitações), nada é cobrado.

---

## 6. Como rodar

**Requisitos:** Python 3.13, uma chave da API do Gemini.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # preencha GEMINI_API_KEY
python -m scripts.validar_cardapio # valida o data/menu.json
python -m scripts.build_index      # gera os embeddings (1 vez)

uvicorn app.main:app --reload      # abra http://127.0.0.1:8000/
```

Outras formas de usar:

```bash
python -m scripts.chat_cli         # conversa no terminal
python -m scripts.buscar "algo sem glúten"   # só a busca semântica
python -m scripts.relatorio_metricas         # custo e latência
python -m eval.run_eval --repeticoes 3       # avaliação com o Gemini real (centavos)
pytest                             # 208 testes, sem chamar a API
```

**Docker** (não precisa de Python instalado; precisa do `.env` com a chave):

```bash
docker compose build
docker compose run --rm app python -m scripts.build_index   # gera os embeddings (1 vez)
docker compose up -d                                        # http://127.0.0.1:8001/
docker compose logs -f app                                  # acompanhar os logs
docker compose down                                         # parar
```

Decisões do Docker: a chave fica só no `.env` (lida em tempo de execução, nunca copiada para a imagem); o container roda como usuário sem privilégios; a porta é publicada apenas em `127.0.0.1` (8001 na sua máquina, para não colidir com o `uvicorn` local na 8000), porque a API não tem autenticação; a pasta `data/` é um volume, então embeddings e métricas sobrevivem a recriações do container.

### Endpoints

| Rota | Função |
|---|---|
| `GET /` | Interface de chat |
| `POST /chat` | `{session_id, mensagem}` → resposta, ferramentas usadas, comanda e métricas |
| `GET /cardapio` | Cardápio completo |
| `GET /metricas` | Resumo de custo e latência |
| `DELETE /sessoes/{id}` | Encerra uma conversa |
| `GET /health` | Saúde do serviço |
| `GET /docs` | Documentação interativa (Swagger) |

### Estrutura

```
app/        agent.py (loop), tools.py, guardrails.py, rag.py, llm.py,
            session.py, cart.py, metrics.py, main.py (API), schemas.py
data/       menu.json (15 pratos)
frontend/   index.html, style.css, app.js
scripts/    utilitários de linha de comando
tests/      208 testes
eval/       eval_set.json (23 casos), checks.py, run_eval.py, ultimo_resultado.json
```

---

## 7. Limitações conhecidas

Sinceridade sobre o que **não** está resolvido:

- **Sessões em memória:** reiniciar o servidor apaga as conversas, e não funciona com várias instâncias.
- **Sem autenticação:** se a API for exposta na internet, qualquer pessoa gasta a sua chave. O teto diário limita, não impede.
- **Detector de alergias por palavras-chave:** cobre só 9 alergênicos e pode registrar alergia a mais (erra para o lado seguro). Não substitui confirmação com a cozinha.
- **Cardápio fictício:** as informações de alergênicos não são de um restaurante real. **Não use este projeto para decisões reais sobre alergia.**
- **O modelo às vezes recusa por conta própria** pratos com alergênico, antes de o guardrail agir. O caminho de confirmação no código existe e é testado, mas foi pouco exercitado com o modelo real (veja 5.3).
- **O escopo é regra de prompt**, não de código: o agente recusou todos os casos fora do restaurante em 3 rodadas, mas isso não é garantia.
- **A API não tem retentativa:** se o Gemini der 429 ou 503, o cliente recebe um erro 502. Na avaliação isso aconteceu em 7 de 69 casos.
- **Plano gratuito:** o erro 429 da avaliação citou `Free Tier` (limite de 15 requisições por minuto), então a chave usada estava num projeto sem faturamento. Nesse plano o conteúdo enviado pode ser usado pelo Google para melhorar seus produtos; use só dados fictícios.
- **Avaliação pequena:** 23 casos, parte escrita depois de ver uma falha; verificações de texto são grosseiras.
- **Custo cresce por turno** (histórico reenviado) e o teto diário é aproximado e em UTC.
- **Falhas não têm custo medido.**
- **Qualidade e latência do modelo variam** entre execuções.

## 8. Próximos passos

- Retentativa com espera (backoff) na API para erros 429 e 503, sem estourar o timeout do cliente.
- Ampliar o conjunto de avaliação (mais perguntas, conversas longas, tentativas de burlar o guardrail) e adicionar um juiz LLM para o que não dá para checar por regra.
- Resumir o histórico antigo para frear o crescimento do custo (a entrada é cerca de 83% dele).
- Armazenamento de sessões compartilhado (Redis) e autenticação.
- Comparar modelos (qualidade × custo × latência) com o mesmo conjunto de avaliação.
- Streaming da resposta para reduzir a latência percebida.
