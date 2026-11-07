/* Interface do atendente virtual. Sem bibliotecas.
   Segurança: todo texto vindo do servidor entra na página como TEXTO (textContent / append),
   nunca como HTML. Por isso uma resposta do modelo não consegue injetar código na página. */
(() => {
  "use strict";

  const MAX_CHARS = 500;
  const TIMEOUT_MS = 90000;

  const SUGESTOES = [
    "Quais pratos não têm lactose?",
    "Quero duas moquecas de camarão",
    "Tenho alergia a amendoim",
    "O que tem na minha comanda?",
  ];

  const ACOES = {
    adicionar_item: "Adicionou à comanda",
    remover_item: "Tirou da comanda",
    ver_carrinho: "Consultou a comanda",
    filtrar_pratos: "Filtrou o cardápio",
  };

  // Quando a ação falha, o rótulo precisa dizer que foi só uma tentativa.
  const ACOES_FALHA = {
    adicionar_item: "Tentou adicionar",
    remover_item: "Tentou tirar",
  };

  // Um texto para cada código de erro que as ferramentas e o guardrail podem devolver.
  const MOTIVOS = {
    alergenico_detectado: "Bloqueado: o prato contém um alergênico que você informou",
    prato_ambiguo: "Há mais de um prato com esse nome",
    prato_nao_encontrado: "Prato não encontrado no cardápio",
    carrinho_invalido: "Quantidade ou item inválido",
    argumentos_invalidos: "Pedido inválido",
    ferramenta_desconhecida: "Pedido inválido",
    alergenico_invalido: "Alergênico não reconhecido no filtro",
    categoria_invalida: "Categoria não reconhecida no filtro",
    preco_invalido: "Preço do filtro inválido",
  };

  const $ = (id) => document.getElementById(id);
  const log = $("log");
  const form = $("form");
  const entrada = $("entrada");
  const botaoEnviar = $("enviar");
  const contador = $("contador");

  let sessionId = novoId();
  let ocupado = false;
  let custoConversa = 0;

  /* ---------- utilitarios ---------- */
  function novoId() {
    const bruto = window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random().toString(36).slice(2)}`;
    return bruto.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
  }

  function el(tag, props = {}, ...filhos) {
    const no = document.createElement(tag);
    for (const [chave, valor] of Object.entries(props)) {
      if (chave === "class") no.className = valor;
      else if (chave === "text") no.textContent = valor;
      else no.setAttribute(chave, valor);
    }
    for (const filho of filhos) if (filho) no.append(filho);
    return no;
  }

  function limpar(no) {
    while (no.firstChild) no.removeChild(no.firstChild);
  }

  function reais(valor) {
    return `R$ ${Number(valor).toFixed(2).replace(".", ",")}`;
  }

  /* ---------- texto do modelo: negrito e listas, sem HTML ---------- */
  function renderInline(pai, texto) {
    for (const parte of texto.split(/(\*\*[^*]+\*\*)/g)) {
      if (/^\*\*[^*]+\*\*$/.test(parte)) pai.append(el("strong", { text: parte.slice(2, -2) }));
      else if (parte) pai.append(parte);
    }
  }

  function renderTexto(recipiente, texto) {
    let lista = null;
    for (const linha of texto.split("\n")) {
      const item = linha.match(/^\s*[*-]\s+(.*)$/);
      if (item) {
        if (!lista) {
          lista = el("ul");
          recipiente.append(lista);
        }
        const li = el("li");
        renderInline(li, item[1]);
        lista.append(li);
      } else {
        lista = null;
        if (linha.trim()) {
          const p = el("p");
          renderInline(p, linha);
          recipiente.append(p);
        }
      }
    }
  }

  /* ---------- conversa ---------- */
  function rolarParaOFim() {
    log.scrollTop = log.scrollHeight;
  }

  function addMensagem(quem, texto) {
    const corpo = el("div", { class: "corpo" });
    if (quem === "atendente") renderTexto(corpo, texto);
    else corpo.textContent = texto;
    const msg = el("div", { class: `msg ${quem}` }, el("span", { class: "autor", text: quem === "atendente" ? "Atendente" : "Você" }), corpo);
    log.append(msg);
    rolarParaOFim();
  }

  function addAviso(titulo, detalhe) {
    const aviso = el("div", { class: "aviso-sistema", role: "alert" }, el("strong", { text: titulo }));
    if (detalhe) aviso.append(detalhe);
    log.append(aviso);
    rolarParaOFim();
  }

  function boasVindas() {
    addMensagem(
      "atendente",
      "Olá! Eu respondo sobre o cardápio, os ingredientes e os alergênicos, e monto seu pedido na comanda. Sou um assistente de IA: se você tem alergia grave, confirme também com a equipe do restaurante.",
    );
  }

  /* ---------- painel lateral ---------- */
  function atualizarComanda(carrinho) {
    const itens = $("itens");
    limpar(itens);
    for (const item of carrinho.itens) {
      itens.append(
        el(
          "li",
          { class: "linha" },
          el("span", {}, `${item.nome} `, el("span", { class: "qtd", text: `× ${item.quantidade}` })),
          el("span", { class: "pontos", "aria-hidden": "true" }),
          el("span", { text: item.subtotal }),
        ),
      );
    }
    $("vazio").hidden = carrinho.itens.length > 0;
    $("total").textContent = carrinho.total;
    const n = carrinho.total_unidades;
    $("resumo-movel").textContent = n > 0 ? `Ver comanda: ${n} ${n === 1 ? "item" : "itens"}, ${carrinho.total}` : "Ver comanda";
  }

  function atualizarAlergias(alergias) {
    const lista = $("alergias");
    limpar(lista);
    for (const a of alergias) lista.append(el("li", { text: `Alergia: ${a}` }));
    $("sem-alergias").hidden = alergias.length > 0;
  }

  function descreverArgs(args) {
    const partes = [];
    if (args.nome_prato) partes.push(args.nome_prato);
    if (args.quantidade) partes.push(`quantidade ${args.quantidade}`);
    if (args.sem_alergenicos) partes.push(`sem ${[].concat(args.sem_alergenicos).join(", ")}`);
    if (args.categoria) partes.push(args.categoria);
    if (args.preco_maximo) partes.push(`até ${reais(args.preco_maximo)}`);
    return partes.join(", ");
  }

  function atualizarAcoes(chamadas) {
    const lista = $("acoes");
    limpar(lista);
    let bloqueou = false;
    for (const c of chamadas) {
      const feito = c.ok === true;
      if (c.erro === "alergenico_detectado") bloqueou = true;
      const detalhe = descreverArgs(c.args || {});
      lista.append(
        el(
          "li",
          {},
          el("span", { class: "titulo", text: (!c.ok && ACOES_FALHA[c.nome]) || ACOES[c.nome] || c.nome }),
          detalhe ? el("span", { class: "detalhe", text: detalhe }) : null,
          el("span", {
            class: feito ? "feito" : "nao-feito",
            text: feito ? "Feito" : MOTIVOS[c.erro] || "Não foi possível",
          }),
        ),
      );
    }
    $("sem-acoes").hidden = chamadas.length > 0;
    const carimbo = $("carimbo");
    carimbo.hidden = !bloqueou;
    if (bloqueou) {
      // reinicia a animacao do carimbo a cada bloqueio
      carimbo.style.animation = "none";
      void carimbo.offsetWidth;
      carimbo.style.animation = "";
    }
  }

  function atualizarMetricas(m) {
    custoConversa += m.custo_usd;
    const dl = $("metricas");
    limpar(dl);
    const linhas = [
      ["Tokens", `${m.tokens_entrada} lidos, ${m.tokens_saida} escritos`],
      ["Chamadas ao modelo", String(m.chamadas_llm)],
      ["Tempo do modelo", `${m.latencia_llm_s.toFixed(1)} s`],
      ["Tempo total", `${m.latencia_total_s.toFixed(1)} s`],
      ["Custo da mensagem", `US$ ${m.custo_usd.toFixed(5)}`],
      ["Custo da conversa", `US$ ${custoConversa.toFixed(5)}`],
    ];
    for (const [nome, valor] of linhas) dl.append(el("dt", { text: nome }), el("dd", { text: valor }));
  }

  function atualizarPainel(dados) {
    atualizarComanda(dados.carrinho);
    atualizarAlergias(dados.alergias);
    atualizarAcoes(dados.chamadas);
    atualizarMetricas(dados.metricas);
  }

  function limparPainel() {
    custoConversa = 0;
    atualizarComanda({ itens: [], total: "R$ 0,00", total_unidades: 0 });
    atualizarAlergias([]);
    atualizarAcoes([]);
    limpar($("metricas"));
  }

  /* ---------- envio ---------- */
  async function mensagemDeErro(resposta) {
    let detalhe = "";
    try {
      const corpo = await resposta.json();
      if (typeof corpo.detail === "string") detalhe = corpo.detail;
    } catch (_) { /* resposta sem JSON */ }
    if (resposta.status === 422) return ["Mensagem não enviada", `Escreva de 1 a ${MAX_CHARS} caracteres e tente de novo.`];
    if (resposta.status === 409) return ["Conversa longa demais", detalhe || "Clique em Nova conversa para continuar."];
    if (resposta.status === 429) return ["Limite de uso atingido", detalhe || "Tente novamente amanhã."];
    if (resposta.status === 502 || resposta.status === 504) return ["O atendente não respondeu", detalhe || "Tente enviar a mensagem de novo."];
    if (resposta.status === 503) return ["Servidor ocupado", detalhe || "Tente de novo em alguns minutos."];
    return ["Algo deu errado", detalhe || `O servidor respondeu com o código ${resposta.status}.`];
  }

  function definirOcupado(valor) {
    ocupado = valor;
    botaoEnviar.disabled = valor;
    log.setAttribute("aria-busy", String(valor));
  }

  async function enviar(texto) {
    texto = texto.trim();
    if (!texto || ocupado) return;
    definirOcupado(true);
    addMensagem("cliente", texto);
    entrada.value = "";
    ajustarCampo();

    const digitando = el("div", { class: "digitando", text: "O atendente está escrevendo" });
    log.append(digitando);
    rolarParaOFim();

    const controle = new AbortController();
    const prazo = setTimeout(() => controle.abort(), TIMEOUT_MS);
    try {
      const resposta = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, mensagem: texto }),
        signal: controle.signal,
      });
      if (!resposta.ok) {
        const [titulo, detalhe] = await mensagemDeErro(resposta);
        addAviso(titulo, detalhe);
        return;
      }
      const dados = await resposta.json();
      addMensagem("atendente", dados.resposta);
      atualizarPainel(dados);
    } catch (erro) {
      if (erro.name === "AbortError") addAviso("A resposta demorou demais", "Tente enviar a mensagem de novo.");
      else addAviso("Sem conexão com o servidor", "Confira se a API está rodando e tente de novo.");
    } finally {
      clearTimeout(prazo);
      digitando.remove();
      definirOcupado(false);
      entrada.focus();
    }
  }

  /* ---------- campo de texto ---------- */
  function ajustarCampo() {
    entrada.style.height = "auto";
    entrada.style.height = `${Math.min(entrada.scrollHeight, 144)}px`;
    const restantes = MAX_CHARS - entrada.value.length;
    contador.textContent = restantes <= 80 ? `${restantes} caracteres restantes` : "";
  }

  entrada.addEventListener("input", ajustarCampo);
  entrada.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    enviar(entrada.value);
  });

  /* ---------- nova conversa, sugestoes e cardapio ---------- */
  function novaConversa() {
    if (ocupado) return;
    const antigo = sessionId;
    sessionId = novoId();
    fetch(`/sessoes/${antigo}`, { method: "DELETE" }).catch(() => {});
    limpar(log);
    limparPainel();
    boasVindas();
    entrada.focus();
  }
  $("nova").addEventListener("click", novaConversa);

  for (const texto of SUGESTOES) {
    const botao = el("button", { type: "button", text: texto });
    botao.addEventListener("click", () => enviar(texto));
    $("sugestoes").append(botao);
  }

  async function carregarCardapio() {
    try {
      const resposta = await fetch("/cardapio");
      if (!resposta.ok) return;
      const pratos = await resposta.json();
      const lista = $("cardapio");
      for (const p of pratos) {
        const contem = p.alergenicos.length ? `Contém: ${p.alergenicos.join(", ")}` : "Sem alergênicos declarados";
        lista.append(
          el(
            "li",
            {},
            el("div", { class: "linha" }, el("span", { text: p.nome }), el("span", { class: "pontos", "aria-hidden": "true" }), el("span", { text: reais(p.preco) })),
            el("span", { class: "contem", text: contem }),
          ),
        );
      }
    } catch (_) { /* o cardapio e so informativo */ }
  }

  boasVindas();
  limparPainel();
  carregarCardapio();
  ajustarCampo();
})();
