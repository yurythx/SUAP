(function () {
    'use strict';

    const INTERVALO_MS = 2000;

    function iniciar() {
        const form = document.querySelector('[data-importacao-siape]');
        if (!form) {
            return;
        }
        const dependencias = JSON.parse(document.getElementById('importacao-siape-dependencias').textContent);
        ligarMarcacao(form, dependencias);
        if (form.dataset.emExecucao === '1') {
            acompanhar(form);
        }
    }

    function caixas(form) {
        return Array.from(form.querySelectorAll('input[name="arquivos"]'));
    }

    function ligarMarcacao(form, dependencias) {
        const avisos = form.querySelector('[data-avisos-dependencias]');
        form.addEventListener('change', function (evento) {
            const caixa = evento.target;
            if (caixa.name !== 'arquivos' || !caixa.dataset.layout) {
                return;
            }
            const mensagens = caixa.checked ? marcarDependencias(form, dependencias, caixa.dataset.layout) : avisarDependentes(form, dependencias, caixa.dataset.layout);
            avisos.textContent = mensagens;
            avisos.hidden = !mensagens;
        });
    }

    function marcarDependencias(form, dependencias, layout) {
        const marcadas = [];
        caixas(form).forEach(function (outra) {
            if (!outra.disabled && !outra.checked && (dependencias[layout] || []).includes(outra.dataset.layout)) {
                outra.checked = true;
                marcadas.push(outra.dataset.layout);
            }
        });
        return marcadas.length ? 'Dependências marcadas junto com ' + layout + ': ' + marcadas.join(', ') + '. Você pode desmarcá-las.' : '';
    }

    function avisarDependentes(form, dependencias, layout) {
        const dependentes = caixas(form)
            .filter(function (outra) { return outra.checked && (dependencias[outra.dataset.layout] || []).includes(layout); })
            .map(function (outra) { return outra.dataset.layout; });
        return dependentes.length ? layout + ' foi desmarcado, mas ' + dependentes.join(', ') + ' depende dele: serão usados os dados já existentes no banco.' : '';
    }

    function acompanhar(form) {
        caixas(form).forEach(function (caixa) { caixa.disabled = true; });
        fetch(form.dataset.progressoUrl, { credentials: 'same-origin' })
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) {
                atualizar(form, dados);
                if (dados.em_execucao) {
                    window.setTimeout(function () { acompanhar(form); }, INTERVALO_MS);
                }
            })
            .catch(function () { window.setTimeout(function () { acompanhar(form); }, INTERVALO_MS * 2); });
    }

    function atualizar(form, dados) {
        const situacao = document.querySelector('[data-situacao-importacao]');
        if (situacao) {
            situacao.textContent = dados.situacao_display;
            situacao.className = 'status ' + dados.classe_status;
        }
        atualizarWorkers(dados);
        dados.arquivos.forEach(function (arquivo) {
            const linha = form.querySelector('tr[data-arquivo="' + arquivo.id + '"]');
            if (!linha) {
                return;
            }
            const rotulo = linha.querySelector('[data-campo="situacao"]');
            rotulo.textContent = arquivo.situacao_display;
            rotulo.className = 'status ' + arquivo.classe_status;
            if (arquivo.motivo) {
                linha.querySelector('[data-campo="motivo"]').textContent = arquivo.motivo.slice(-300);
            }
            const barra = linha.querySelector('[data-campo="progresso"] progress');
            definirProgresso(barra, barra.nextElementSibling, arquivo.percentual);
            linha.querySelector('[data-campo="falhas"]').textContent = arquivo.falhas;
            linha.querySelector('[data-campo="avisos"]').textContent = arquivo.avisos;
            atualizarGradeDeLotes(linha, arquivo);
        });
    }

    function formatarInteiro(numero) {
        return Number(numero).toLocaleString('pt-BR');
    }

    function criarCelula(texto) {
        const celula = document.createElement('td');
        celula.textContent = texto;
        return celula;
    }

    function formatoProgressoPython(percentual) {
        // Espelha `round(float(percent), 2)` + `str(...)` da tag `{% progressbar %}`
        // (djtools/templatetags/tags/utils.py): valor inteiro sempre com uma casa decimal
        // (68 -> '68.0'), porque o CSS do tema seleciona a cor da barra por `data-progress`.
        const arredondado = Math.round(percentual * 100) / 100;
        return Number.isInteger(arredondado) ? arredondado.toFixed(1) : String(arredondado);
    }

    function definirProgresso(barra, rotulo, percentual) {
        barra.value = percentual;
        barra.dataset.progress = 'p' + formatoProgressoPython(percentual) + '%';
        rotulo.textContent = percentual + '%';
    }

    function criarProgressoContainer(percentual) {
        const container = document.createElement('div');
        container.className = 'progressbar-container';
        const barra = document.createElement('progress');
        barra.max = 100;
        const rotulo = document.createElement('span');
        definirProgresso(barra, rotulo, percentual);
        container.appendChild(barra);
        container.appendChild(rotulo);
        return container;
    }

    function criarLinhaWorker(worker) {
        const linha = document.createElement('tr');
        linha.appendChild(criarCelula(worker.rotulo));
        linha.appendChild(criarCelula(worker.layout));
        linha.appendChild(criarCelula(worker.lote + ' de ' + worker.total_lotes));
        linha.appendChild(criarCelula(formatarInteiro(worker.processadas) + ' de ' + formatarInteiro(worker.total_linhas)));
        const celulaProgresso = document.createElement('td');
        celulaProgresso.appendChild(criarProgressoContainer(worker.percentual));
        linha.appendChild(celulaProgresso);
        return linha;
    }

    function criarLinhaSemWorkers() {
        const linha = document.createElement('tr');
        const celula = document.createElement('td');
        celula.colSpan = 5;
        celula.textContent = 'Nenhum lote em execução no momento.';
        linha.appendChild(celula);
        return linha;
    }

    function atualizarWorkers(dados) {
        const caixa = document.querySelector('[data-workers-agora]');
        if (!caixa) {
            return;
        }
        caixa.hidden = !dados.em_execucao;
        const corpo = caixa.querySelector('[data-workers-corpo]');
        while (corpo.firstChild) {
            corpo.removeChild(corpo.firstChild);
        }
        if (!dados.workers.length) {
            corpo.appendChild(criarLinhaSemWorkers());
            return;
        }
        dados.workers.forEach(function (worker) { corpo.appendChild(criarLinhaWorker(worker)); });
    }

    function resumirLotes(lotes) {
        const total = lotes.length;
        const concluidos = lotes.filter(function (lote) { return lote.situacao === 'concluido'; }).length;
        const executando = lotes.filter(function (lote) { return lote.situacao === 'executando'; }).length;
        const falhas = lotes.filter(function (lote) { return lote.situacao === 'falhou'; }).length;
        const pulados = lotes.filter(function (lote) { return lote.situacao === 'pulado'; }).length;
        const fila = total - concluidos - executando - falhas - pulados;
        return total + ' lotes · ' + concluidos + ' concluídos · ' + executando + ' em execução · ' + fila + ' na fila · ' + pulados + ' pulados · ' + falhas + ' com falha';
    }

    function criarBadgeLote(lote) {
        const badge = document.createElement('span');
        badge.className = 'status ' + lote.classe_status;
        badge.dataset.lote = lote.id;
        badge.title = 'Lote ' + lote.numero + ' · ' + lote.processadas + ' de ' + lote.total_linhas + ' linhas · worker ' + (lote.worker || '-') + ' · ' + lote.falhas + ' falhas';
        badge.textContent = lote.situacao === 'executando' ? lote.numero + ' · ' + lote.percentual + '%' : String(lote.numero);
        return badge;
    }

    function criarLinhaDeLotes(arquivoId, colunas) {
        const linha = document.createElement('tr');
        linha.dataset.lotesDe = arquivoId;
        const celula = document.createElement('td');
        celula.colSpan = colunas;
        const resumo = document.createElement('p');
        resumo.className = 'help';
        resumo.dataset.campo = 'resumo-lotes';
        const badges = document.createElement('div');
        badges.dataset.campo = 'badges-lotes';
        celula.appendChild(resumo);
        celula.appendChild(badges);
        linha.appendChild(celula);
        return linha;
    }

    function atualizarGradeDeLotes(linhaArquivo, arquivo) {
        if (arquivo.lotes.length <= 1) {
            return;
        }
        const form = linhaArquivo.closest('form');
        let linhaLotes = form.querySelector('tr[data-lotes-de="' + arquivo.id + '"]');
        if (!linhaLotes) {
            linhaLotes = criarLinhaDeLotes(arquivo.id, linhaArquivo.children.length);
            linhaArquivo.insertAdjacentElement('afterend', linhaLotes);
        }
        linhaLotes.querySelector('[data-campo="resumo-lotes"]').textContent = resumirLotes(arquivo.lotes);
        const badges = linhaLotes.querySelector('[data-campo="badges-lotes"]');
        while (badges.firstChild) {
            badges.removeChild(badges.firstChild);
        }
        arquivo.lotes.forEach(function (lote, indice) {
            if (indice > 0) {
                badges.appendChild(document.createTextNode(' '));
            }
            badges.appendChild(criarBadgeLote(lote));
        });
    }

    document.addEventListener('DOMContentLoaded', iniciar);
})();
