(function () {
    function getCsrfToken() {
        const input = document.querySelector('#js-csrf [name="csrfmiddlewaretoken"]');
        return input ? input.value : '';
    }

    function clampNonNegativeInt(value) {
        const parsed = parseInt(value || '0', 10);
        if (!isFinite(parsed) || isNaN(parsed)) return 0;
        return Math.max(0, parsed);
    }

    function formatPtBr2(value) {
        const n = Number(value);
        if (!isFinite(n)) return '0,00';
        return n.toFixed(2).replace('.', ',');
    }

    function clampPercent(value) {
        const n = Number(value);
        if (!isFinite(n)) return 0;
        return Math.min(100, Math.max(0, n));
    }

    function atualizarProgressbar(hostId, percentValue) {
        const host = document.getElementById(hostId);
        if (!host) return;

        const container = host.querySelector('.progressbar-container');
        if (!container) return;

        const progress = container.querySelector('progress');
        const label = container.querySelector('span');
        if (!progress || !label) return;

        const p = clampPercent(percentValue);
        const pDisplay2 = Math.round(p * 100) / 100; // 2 casas
        progress.value = String(pDisplay2);
        progress.setAttribute('data-progress', `p${pDisplay2}%`);
        label.textContent = `${Math.round(p)}%`;
    }

    function setTabChecked(tabName, ok) {
        // Alterna o ícone de "check" na aba principal correspondente (djtools tabs.js usa a classe .checked).
        const btn = document.querySelector(`.nav-tabs .nav-link[data-tab="${tabName}"]`);
        if (btn) btn.classList.toggle('checked', !!ok);
    }

    function aplicarResumo(resumo) {
        if (!resumo) return;

        const totalPontosEls = document.querySelectorAll('.js-total-pontos');
        const itensPreenchidosEls = document.querySelectorAll('.js-itens-preenchidos');

        totalPontosEls.forEach(el => {
            el.textContent = formatPtBr2(resumo.total_pontos);
        });
        itensPreenchidosEls.forEach(el => {
            el.textContent = String(resumo.itens_preenchidos);
        });

        atualizarProgressbar('js-progress-pontos', resumo.pontos_percent);
        atualizarProgressbar('js-progress-itens', resumo.itens_percent);

        // Requisito obrigatório (RN04): atualiza o indicador quando aplicável.
        const reqObrig = resumo.requisito_obrigatorio;
        const reqObrigEl = document.getElementById('js-requisito-obrigatorio-status');
        if (reqObrig && reqObrigEl) {
            reqObrigEl.innerHTML = reqObrig.alcancado
                ? '<span class="status status-success">Alcançado</span>'
                : '<span class="status status-alert">Pendente</span>';
        }

        // Quanto falta para o mínimo de pontos.
        const faltamEl = document.getElementById('js-pontos-faltam');
        if (faltamEl) {
            const faltam = Math.max(0, Number(resumo.pontos_minimos) - Number(resumo.total_pontos));
            faltamEl.textContent = faltam > 0 ? `faltam ${formatPtBr2(faltam)} pts` : 'mínimo atingido';
        }

        // Quebra de pontos por requisito.
        const breakdownEl = document.getElementById('js-pontos-por-requisito');
        if (breakdownEl && Array.isArray(resumo.pontos_por_requisito)) {
            breakdownEl.innerHTML = resumo.pontos_por_requisito
                .map((r) => `<span class="rsc-requisito-chip badge ms-0"><strong>${r.numeral}</strong> ${r.pontos}</span>`)
                .join('');
        }

        // Ícone de "check" da aba Formulário (ao vivo): pontos + itens mínimos + requisito obrigatório (RN04).
        const min = Number(resumo.pontos_minimos);
        const itensMin = Number(resumo.itens_minimos);
        const pontosOk = !(min > 0) || Number(resumo.total_pontos) >= min;
        const itensOk = !(itensMin > 0) || Number(resumo.itens_preenchidos) >= itensMin;
        const rn04Ok = !reqObrig || !reqObrig.aplicavel || reqObrig.alcancado;
        setTabChecked('formulario', pontosOk && itensOk && rn04Ok);
    }

    function getProcessoId() {
        const m = window.location.pathname.match(/\/visualizar\/(\d+)\/?/);
        return m ? m[1] : null;
    }

    function getItemIdFromInput(input) {
        const name = (input.getAttribute('name') || '').toString();
        const m = name.match(/^quantidade_(\d+)$/);
        return m ? m[1] : null;
    }

    // ---------------------- Sticky (fallback) ----------------------
    (function initResumoSticky() {
        // Flutuação desativada por hora: atrapalhava usuários com telas menores (notebooks).
        // O card fica no fluxo normal; para reativar, mudar FLUTUACAO_ATIVA para true (e o CSS).
        const FLUTUACAO_ATIVA = false;
        const resumo = document.querySelector('.rsc-resumo-sticky');
        const placeholder = document.querySelector('.rsc-resumo-placeholder');
        if (!FLUTUACAO_ATIVA || !resumo || !placeholder) return;

        const threshold = 16; // px

        function fixar() {
            if (resumo.classList.contains('is-fixed')) return;
            const h = resumo.getBoundingClientRect().height;
            placeholder.style.display = 'block';
            placeholder.style.height = `${h}px`;
            resumo.classList.add('is-fixed');
        }

        function desfixar() {
            if (!resumo.classList.contains('is-fixed')) return;
            resumo.classList.remove('is-fixed');
            placeholder.style.display = 'none';
            placeholder.style.height = '';
        }

        function estaOculto() {
            // Em aba inativa (display:none), o elemento reporta rect zerado. Nesse estado
            // as medições são inválidas — não se deve fixar/desfixar com base nelas.
            const r = resumo.getBoundingClientRect();
            return r.width === 0 && r.height === 0;
        }

        function avaliar() {
            if (estaOculto()) return;

            if (resumo.classList.contains('is-fixed')) {
                const p = placeholder.getBoundingClientRect();
                if (p.top >= threshold + 1) desfixar();
                return;
            }

            const r = resumo.getBoundingClientRect();
            if (r.top <= threshold) fixar();
        }

        document.addEventListener('scroll', avaliar, true);
        window.addEventListener('resize', avaliar);
        setTimeout(avaliar, 0);

        // Ao trocar de aba, o estado fixo pode ter "vazado" de uma medição feita com a aba
        // oculta. Reseta e reavalia no próximo frame, quando o layout da aba ativa estabilizou.
        const prevOnChangeTabs = window.onChangeTabs;
        window.onChangeTabs = function () {
            try {
                desfixar();
                requestAnimationFrame(avaliar);
            } finally {
                if (typeof prevOnChangeTabs === 'function') prevOnChangeTabs();
            }
        };
    })();

    // ---------------------- Autosave (quantidade) ----------------------
    (function initAutosave() {
        const statusEl = document.getElementById('js-autosave-status');
        function setStatus(text) {
            if (!statusEl) return;
            statusEl.textContent = text || '';
        }

        async function salvarQuantidade(itemId, quantidade) {
            const processoId = getProcessoId();
            if (!processoId) return;
            const url = `/rsc_tae/processo/${processoId}/item/${itemId}/salvar_quantidade/`;

            setStatus('Salvando...');
            const resp = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    quantidade: String(quantidade),
                    csrfmiddlewaretoken: getCsrfToken(),
                }),
            });
            if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
            const data = await resp.json();
            if (!data.ok) throw new Error(data.msg || 'Erro ao salvar');
            return data;
        }

        const debounceTimers = new Map();
        function debounce(key, ms, fn) {
            if (debounceTimers.has(key)) clearTimeout(debounceTimers.get(key));
            const t = setTimeout(() => {
                debounceTimers.delete(key);
                fn();
            }, ms);
            debounceTimers.set(key, t);
        }

        document.querySelectorAll('.rsc-tabela-saberes tbody tr').forEach((tr) => {
            const input = tr.querySelector('.js-quantidade');
            const minus = tr.querySelector('.js-qtd-minus');
            const plus = tr.querySelector('.js-qtd-plus');
            if (!input || !minus || !plus) return;

            const itemId = getItemIdFromInput(input);
            if (itemId) {
                input.addEventListener('input', () => {
                    const qtd = clampNonNegativeInt(input.value);
                    debounce(`qtd:${itemId}`, 500, async () => {
                        try {
                            const data = await salvarQuantidade(itemId, qtd);
                            aplicarResumo(data.resumo);
                            setStatus('Salvo');
                            setTimeout(() => setStatus(''), 1200);
                        } catch (e) {
                            console.error(e);
                            setStatus('Erro ao salvar');
                        }
                    });
                });
            }

            minus.addEventListener('click', () => {
                const next = clampNonNegativeInt(input.value) - 1;
                input.value = String(Math.max(0, next));
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });

            plus.addEventListener('click', () => {
                const next = clampNonNegativeInt(input.value) + 1;
                input.value = String(next);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });
    })();

    // ---------------------- Anexos ----------------------
    (function initAnexos() {
        function parsePtBrNumber(value) {
            const normalized = String(value || '').trim().replace(/\./g, '').replace(',', '.');
            const n = Number(normalized);
            if (!isFinite(n) || isNaN(n)) return 0;
            return Math.max(0, n);
        }

        function formatPtBr2str(value) {
            return formatPtBr2(value);
        }

        function getStepFromInput(inputEl) {
            const raw = inputEl && inputEl.dataset ? inputEl.dataset.step : null;
            const n = Number(raw);
            return isFinite(n) && !isNaN(n) && n > 0 ? n : 1;
        }
        function canEditAnexos() {
            const meta = document.getElementById('js-rsc-meta');
            return meta && meta.dataset && meta.dataset.ehDono === '1';
        }

        function isItemTemporal(itemId) {
            const ul = document.querySelector(`.js-anexos-list[data-item-id="${itemId}"]`);
            return ul && ul.dataset.itemTemporal === '1';
        }

        /**
         * Calcula e formata a duração entre duas datas em anos, meses e dias.
         *
         * Espelha o backend (rsc_tae/models/anexo.py): decomposição de calendário com a
         * data de fim INCLUSIVA (conta o último dia). A conversão em anos pontuáveis
         * ('ano ou fração superior a 6 meses') é feita no total do item, não aqui.
         *
         * @param {string} dataInicio - Data inicial no formato 'YYYY-MM-DD'
         * @param {string} dataFim    - Data final no formato 'YYYY-MM-DD'
         * @returns {string} Texto formatado (ex: "2 anos, 6 meses, 1 dia") ou
         *                   'Informe o período' se as datas forem inválidas/ausentes.
         */
        function calcularPeriodoDisplay(dataInicio, dataFim) {

            // Sem período utilizável enquanto as duas datas não forem informadas
            if (!dataInicio || !dataFim) return 'Informe o período';

            // Fixa meia-noite para evitar distorções de fuso horário
            const d0 = new Date(dataInicio + 'T00:00:00');
            const d1 = new Date(dataFim + 'T00:00:00');
            if (isNaN(d0) || isNaN(d1) || d1 < d0) return 'Informe o período';

            // Fim inclusivo: soma 1 dia para contar o último dia do período
            const fim = new Date(d1);
            fim.setDate(fim.getDate() + 1);

            let anos  = fim.getFullYear() - d0.getFullYear();
            let meses = fim.getMonth() - d0.getMonth();
            let dias  = fim.getDate() - d0.getDate();

            if (dias < 0) {
                meses -= 1;
                // dias do mês imediatamente anterior a "fim"
                dias += new Date(fim.getFullYear(), fim.getMonth(), 0).getDate();
            }
            if (meses < 0) {
                anos -= 1;
                meses += 12;
            }

            const partes = [];
            if (anos)  partes.push(anos === 1  ? '1 ano'  : anos + ' anos');
            if (meses) partes.push(meses === 1 ? '1 mês'  : meses + ' meses');
            if (dias)  partes.push(dias === 1  ? '1 dia'  : dias + ' dias');

            return partes.join(', ') || 'Informe o período';
        }

        function atualizarPontuacaoItem(itemId, pontuacaoTotalItem) {
            const nodes = document.querySelectorAll(`.js-pontuacao-item-total[data-item-id="${itemId}"]`);
            nodes.forEach((n) => {
                n.textContent = formatPtBr2(pontuacaoTotalItem);
            });
        }

        // Atualiza TODAS as listas do item (não só a primeira): panes de aba podem manter
        // mais de uma cópia da lista no DOM, e atualizar só uma deixava a outra com o
        // estado do servidor (mensagem "Nenhum documento anexado" persistente/duplicada).
        function renderLista(itemId, anexos, itemTemporal) {
            const uls = document.querySelectorAll(`.js-anexos-list[data-item-id="${itemId}"]`);
            uls.forEach((ul) => renderListaNoUl(ul, itemId, anexos, itemTemporal));
        }

        function renderListaNoUl(ul, itemId, anexos, itemTemporal) {
            if (!ul) return;

            // Detecta item_temporal: argumento explícito > data attribute desta lista
            const temporal = typeof itemTemporal !== 'undefined' ? !!itemTemporal : ul.dataset.itemTemporal === '1';
            if (typeof itemTemporal !== 'undefined') {
                ul.dataset.itemTemporal = itemTemporal ? '1' : '0';
            }

            ul.innerHTML = '';
            if (!anexos || anexos.length === 0) {
                const li = document.createElement('li');
                const p = document.createElement('p');
                p.className = 'alert alert-warning mb-0';
                p.textContent = 'Nenhum documento anexado. São aceitos apenas arquivos em formato PDF.';
                li.appendChild(p);
                ul.appendChild(li);
                return;
            }

            const editable = canEditAnexos();
            const aceitaPapel = ul.dataset.itemAceitaPapel === '1';

            anexos.forEach((a) => {
                const li = document.createElement('li');

                const nomeWrap = document.createElement('div');
                nomeWrap.className = 'rsc-anexo-nome';

                const link = document.createElement('a');
                link.href = a.url || '#';
                link.target = '_blank';
                link.rel = 'noopener';
                link.textContent = a.nome || 'Arquivo';
                link.title = a.nome || 'Arquivo';
                nomeWrap.appendChild(link);

                let descricaoNode = null;
                if (editable) {
                    const dLabel = document.createElement('label');
                    dLabel.className = 'rsc-anexo-campo rsc-anexo-campo--descricao';
                    const dSpan = document.createElement('span');
                    dSpan.textContent = 'Descrição ';
                    const dReq = document.createElement('span');
                    dReq.className = 'rsc-obrigatorio';
                    dReq.title = 'Obrigatório';
                    dReq.textContent = '*';
                    dSpan.appendChild(dReq);
                    const dInput = document.createElement('textarea');
                    dInput.rows = 2;
                    dInput.className = 'js-anexo-descricao rsc-anexo-descricao-input' + ((a.descricao || '').trim() ? '' : ' rsc-campo-invalido');
                    dInput.value = a.descricao || '';
                    dInput.dataset.anexoId = String(a.id);
                    dInput.dataset.itemId = String(itemId);
                    dInput.setAttribute('placeholder', 'Descrição do documento (obrigatória)');
                    dInput.setAttribute('aria-label', 'Descrição do documento');
                    dLabel.appendChild(dSpan);
                    dLabel.appendChild(dInput);
                    descricaoNode = dLabel;
                } else if (a.descricao) {
                    const ro = document.createElement('div');
                    ro.className = 'rsc-anexo-descricao-readonly text-muted';
                    const strong = document.createElement('strong');
                    strong.textContent = 'Descrição: ';
                    ro.appendChild(strong);
                    ro.appendChild(document.createTextNode(a.descricao));
                    descricaoNode = ro;
                }

                let pontosNode = null;
                if (temporal && editable) {
                    // Renderiza campos de data para itens temporais
                    const control = document.createElement('div');
                    control.className = 'rsc-anexo-datas';
                    control.setAttribute('role', 'group');
                    control.setAttribute('aria-label', 'Período do documento');

                    const labelInicio = document.createElement('label');
                    labelInicio.className = 'rsc-data-label';
                    labelInicio.textContent = 'Início ';
                    const inputInicio = document.createElement('input');
                    inputInicio.type = 'date';
                    inputInicio.className = 'js-anexo-data-inicio rsc-data-input';
                    inputInicio.dataset.anexoId = String(a.id);
                    inputInicio.dataset.itemId = String(itemId);
                    inputInicio.value = a.data_inicio || '';
                    labelInicio.appendChild(inputInicio);

                    const labelFim = document.createElement('label');
                    labelFim.className = 'rsc-data-label';
                    labelFim.textContent = 'Fim ';
                    const inputFim = document.createElement('input');
                    inputFim.type = 'date';
                    inputFim.className = 'js-anexo-data-fim rsc-data-input';
                    inputFim.dataset.anexoId = String(a.id);
                    inputFim.dataset.itemId = String(itemId);
                    inputFim.value = a.data_fim || '';
                    labelFim.appendChild(inputFim);

                    const periodo = document.createElement('span');
                    periodo.className = 'status status-info rsc-periodo-display js-periodo-display';
                    periodo.dataset.anexoId = String(a.id);
                    periodo.textContent = a.periodo_display || calcularPeriodoDisplay(a.data_inicio, a.data_fim);

                    control.appendChild(labelInicio);
                    control.appendChild(labelFim);
                    control.appendChild(periodo);
                    pontosNode = control;
                } else if (temporal && !editable) {
                    const ro = document.createElement('div');
                    ro.className = 'rsc-anexo-datas-readonly text-muted';
                    if (a.data_inicio && a.data_fim) {
                        const di = a.data_inicio.split('-').reverse().join('/');
                        const df = a.data_fim.split('-').reverse().join('/');
                        ro.innerHTML = di + ' a ' + df + ' &mdash; <strong>' + (a.periodo_display || '') + '</strong>';
                    } else {
                        ro.textContent = 'Período não informado';
                    }
                    pontosNode = ro;
                } else if (editable) {
                    const control = document.createElement('div');
                    control.className = 'rsc-anexo-pontos';
                    control.setAttribute('role', 'group');
                    control.setAttribute('aria-label', 'Unidades do arquivo');

                    const minus = document.createElement('button');
                    minus.type = 'button';
                    minus.className = 'btn default rsc-anexo-pontos-btn js-anexo-pontos-minus no-confirm';
                    minus.dataset.anexoId = String(a.id);
                    minus.setAttribute('aria-label', 'Diminuir unidades');
                    const iMinus = document.createElement('span');
                    iMinus.className = 'icone fas fa-minus';
                    iMinus.setAttribute('aria-hidden', 'true');
                    minus.appendChild(iMinus);

                    const input = document.createElement('input');
                    input.type = 'text';
                    input.value = formatPtBr2str(a.pontuacao || 0);
                    input.className = 'js-anexo-pontuacao rsc-anexo-pontos-input';
                    input.setAttribute('inputmode', 'decimal');
                    input.setAttribute('autocomplete', 'off');
                    input.dataset.anexoId = String(a.id);
                    input.dataset.itemId = String(itemId);
                    input.dataset.step = '1';
                    input.setAttribute('aria-label', 'Unidades');

                    const plus = document.createElement('button');
                    plus.type = 'button';
                    plus.className = 'btn default rsc-anexo-pontos-btn js-anexo-pontos-plus';
                    plus.dataset.anexoId = String(a.id);
                    plus.setAttribute('aria-label', 'Aumentar unidades');
                    const iPlus = document.createElement('span');
                    iPlus.className = 'icone fas fa-plus';
                    iPlus.setAttribute('aria-hidden', 'true');
                    plus.appendChild(iPlus);

                    control.appendChild(minus);
                    control.appendChild(input);
                    control.appendChild(plus);
                    pontosNode = control;
                } else {
                    const ro = document.createElement('div');
                    ro.className = 'rsc-anexo-pontos-readonly text-muted';
                    ro.textContent = `${formatPtBr2(a.pontuacao)} pts`;
                    pontosNode = ro;
                }

                // Envolve o controle num campo rotulado (Unidades/Período) quando editável
                let pontosCampo = pontosNode;
                if (editable && pontosNode) {
                    const wrap = document.createElement('div');
                    wrap.className = 'rsc-anexo-campo';
                    const span = document.createElement('span');
                    span.textContent = temporal ? 'Período' : 'Unidades';
                    wrap.appendChild(span);
                    wrap.appendChild(pontosNode);
                    pontosCampo = wrap;
                }

                const acoes = document.createElement('span');
                acoes.className = 'rsc-anexos-acoes';

                const aView = document.createElement('a');
                aView.className = 'btn default no-confirm';
                aView.href = a.url || '#';
                aView.target = '_blank';
                aView.rel = 'noopener';
                aView.setAttribute('aria-label', 'Visualizar anexo');

                const iView = document.createElement('span');
                iView.className = 'icone fas fa-eye';
                iView.setAttribute('aria-hidden', 'true');
                aView.appendChild(iView);

                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn danger no-confirm js-excluir-anexo';
                btn.dataset.anexoId = String(a.id);

                const iTrash = document.createElement('span');
                iTrash.className = 'icone fas fa-trash';
                iTrash.setAttribute('aria-hidden', 'true');
                btn.appendChild(iTrash);

                acoes.appendChild(aView);
                if (editable) acoes.appendChild(btn);

                li.className = 'rsc-anexo-card';
                const topo = document.createElement('div');
                topo.className = 'rsc-anexo-card__topo';
                topo.appendChild(nomeWrap);
                topo.appendChild(acoes);

                // Seletor de papel (titular/substituto) dos itens do Requisito V
                let papelCampo = null;
                if (aceitaPapel && editable) {
                    papelCampo = document.createElement('div');
                    papelCampo.className = 'rsc-anexo-campo';
                    const spanP = document.createElement('span');
                    spanP.innerHTML = 'Papel <abbr title="Obrigatório" class="rsc-obrigatorio">*</abbr>';
                    const grupo = document.createElement('div');
                    grupo.className = 'rsc-anexo-papel' + (a.papel ? '' : ' rsc-campo-invalido');
                    grupo.setAttribute('role', 'radiogroup');
                    grupo.setAttribute('aria-label', 'Papel do documento');
                    grupo.dataset.anexoId = String(a.id);
                    ['titular', 'substituto'].forEach((val) => {
                        const lbl = document.createElement('label');
                        const rb = document.createElement('input');
                        rb.type = 'radio';
                        rb.name = 'papel-' + a.id;
                        rb.value = val;
                        rb.className = 'js-anexo-papel';
                        rb.dataset.anexoId = String(a.id);
                        rb.dataset.itemId = String(itemId);
                        if (a.papel === val) rb.checked = true;
                        lbl.appendChild(rb);
                        lbl.appendChild(document.createTextNode(' ' + (val === 'titular' ? 'Titular' : 'Substituto')));
                        grupo.appendChild(lbl);
                    });
                    papelCampo.appendChild(spanP);
                    papelCampo.appendChild(grupo);
                }

                const campos = document.createElement('div');
                campos.className = 'rsc-anexo-card__campos';
                if (descricaoNode) campos.appendChild(descricaoNode);
                if (papelCampo) campos.appendChild(papelCampo);
                if (pontosCampo) campos.appendChild(pontosCampo);

                li.appendChild(topo);
                li.appendChild(campos);
                ul.appendChild(li);
            });
        }

        async function carregarLista(itemId) {
            const processoId = getProcessoId();
            if (!processoId) return;
            const url = `/rsc_tae/processo/${processoId}/item/${itemId}/anexos/`;
            const resp = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
            const data = await resp.json();
            if (!data.ok) throw new Error(data.msg || 'Erro ao carregar anexos');
            renderLista(itemId, data.anexos, data.item_temporal);
            if (typeof data.pontuacao_total_item !== 'undefined') atualizarPontuacaoItem(itemId, data.pontuacao_total_item);
            if (data.resumo) aplicarResumo(data.resumo);
        }

        const debounceTimers = new Map();
        function debounce(key, ms, fn) {
            if (debounceTimers.has(key)) clearTimeout(debounceTimers.get(key));
            const t = setTimeout(() => {
                debounceTimers.delete(key);
                fn();
            }, ms);
            debounceTimers.set(key, t);
        }

        async function salvarPontuacaoAnexo(processoId, anexoId, pontuacao) {
            const url = `/rsc_tae/processo/${processoId}/anexo/${anexoId}/salvar_pontuacao/`;
            const resp = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    pontuacao: String(pontuacao),
                    csrfmiddlewaretoken: getCsrfToken(),
                }),
            });
            if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
            const data = await resp.json();
            if (!data.ok) throw new Error(data.msg || 'Erro ao salvar pontuação');
            return data;
        }

        // Anexar documento: seleciona o arquivo e envia imediatamente (a descrição
        // é preenchida depois, no card "Documentos anexados").
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'application/pdf,.pdf';
        fileInput.style.display = 'none';
        document.body.appendChild(fileInput);

        let itemIdAtual = null;

        document.addEventListener('click', async (ev) => {
            const btnAnexar = ev.target.closest('.js-anexar-documentos');
            if (btnAnexar) {
                itemIdAtual = btnAnexar.dataset.itemId;
                fileInput.value = '';
                fileInput.click();
                return;
            }

            const btnExcluir = ev.target.closest('.js-excluir-anexo');
            if (btnExcluir) {
                const processoId = getProcessoId();
                if (!processoId) return;
                const anexoId = btnExcluir.dataset.anexoId;
                if (!anexoId) return;
                if (!confirm('Deseja realmente excluir este anexo?')) return;

                const url = `/rsc_tae/processo/${processoId}/anexo/${anexoId}/excluir/`;
                try {
                    const resp = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest',
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: new URLSearchParams({ csrfmiddlewaretoken: getCsrfToken() }),
                    });
                    if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
                    const data = await resp.json();
                    if (!data.ok) throw new Error(data.msg || 'Erro ao excluir');

                    const ul = btnExcluir.closest('.js-anexos-list');
                    const itemId = ul ? ul.dataset.itemId : null;
                    if (itemId) await carregarLista(itemId);
                } catch (e) {
                    console.error(e);
                    alert('Não foi possível excluir o anexo.');
                }
            }
        });

        fileInput.addEventListener('change', async () => {
            const processoId = getProcessoId();
            if (!processoId || !itemIdAtual) return;
            const file = fileInput.files && fileInput.files[0];
            if (!file) return;

            const url = `/rsc_tae/processo/${processoId}/item/${itemIdAtual}/anexos/upload/`;
            const formData = new FormData();
            formData.append('arquivo', file);
            formData.append('csrfmiddlewaretoken', getCsrfToken());

            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData,
                });
                if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
                const data = await resp.json();
                if (!data.ok) throw new Error(data.msg || 'Erro ao anexar');

                await carregarLista(itemIdAtual);
            } catch (e) {
                console.error(e);
                alert('Não foi possível anexar o arquivo.');
            } finally {
                itemIdAtual = null;
            }
        });

        // Autosave pontuação por anexo + botões +/-
        document.addEventListener('input', (ev) => {
            const input = ev.target && ev.target.closest ? ev.target.closest('.js-anexo-pontuacao') : null;
            if (!input) return;
            const processoId = getProcessoId();
            if (!processoId) return;
            const anexoId = input.dataset.anexoId;
            const itemId = input.dataset.itemId;
            if (!anexoId || !itemId) return;

            const pontuacao = parsePtBrNumber(input.value);
            debounce(`anexo:${anexoId}`, 500, async () => {
                try {
                    const data = await salvarPontuacaoAnexo(processoId, anexoId, pontuacao);
                    if (typeof data.pontuacao_total_item !== 'undefined') atualizarPontuacaoItem(itemId, data.pontuacao_total_item);
                    if (data.resumo) aplicarResumo(data.resumo);
                } catch (e) {
                    console.error(e);
                }
            });
        });

        document.addEventListener('blur', (ev) => {
            const input = ev.target && ev.target.closest ? ev.target.closest('.js-anexo-pontuacao') : null;
            if (!input) return;
            const n = parsePtBrNumber(input.value);
            input.value = formatPtBr2str(n);
        }, true);

        document.addEventListener('click', (ev) => {
            const minus = ev.target.closest('.js-anexo-pontos-minus');
            const plus = ev.target.closest('.js-anexo-pontos-plus');
            if (!minus && !plus) return;

            const anexoId = (minus || plus).dataset.anexoId;
            if (!anexoId) return;
            const input = document.querySelector(`.js-anexo-pontuacao[data-anexo-id="${anexoId}"]`);
            if (!input) return;

            const current = parsePtBrNumber(input.value);
            const step = getStepFromInput(input);
            const next = minus ? Math.max(0, current - step) : current + step;
            input.value = formatPtBr2str(next);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        });

        // Autosave da descrição por anexo (edição inline no card)
        async function salvarDescricaoAnexo(processoId, anexoId, descricao) {
            const url = `/rsc_tae/processo/${processoId}/anexo/${anexoId}/salvar_descricao/`;
            const resp = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({ descricao: descricao, csrfmiddlewaretoken: getCsrfToken() }),
            });
            if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
            const data = await resp.json();
            if (!data.ok) throw new Error(data.msg || 'Erro ao salvar descrição');
            return data;
        }

        document.addEventListener('input', (ev) => {
            const input = ev.target && ev.target.closest ? ev.target.closest('.js-anexo-descricao') : null;
            if (!input) return;
            const processoId = getProcessoId();
            if (!processoId) return;
            const anexoId = input.dataset.anexoId;
            if (!anexoId) return;
            const descricao = input.value.trim();
            input.classList.toggle('rsc-campo-invalido', !descricao);
            if (!descricao) return; // vazio: não salva; a conclusão do preenchimento bloqueia
            debounce(`desc:${anexoId}`, 500, async () => {
                try {
                    await salvarDescricaoAnexo(processoId, anexoId, descricao);
                } catch (e) {
                    console.error(e);
                }
            });
        });

        // Autosave datas para itens temporais
        async function salvarDatasAnexo(processoId, anexoId, dataInicio, dataFim, papel) {
            const url = `/rsc_tae/processo/${processoId}/anexo/${anexoId}/salvar_pontuacao/`;
            const params = {
                data_inicio: dataInicio || '',
                data_fim: dataFim || '',
                csrfmiddlewaretoken: getCsrfToken(),
            };
            if (papel) params.papel = papel; // só envia quando há papel selecionado (evita limpar)
            const resp = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams(params),
            });
            if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
            const data = await resp.json();
            if (!data.ok) throw new Error(data.msg || 'Erro ao salvar datas');
            return data;
        }

        document.addEventListener('change', (ev) => {
            const input = ev.target && ev.target.closest ? ev.target.closest('.js-anexo-data-inicio, .js-anexo-data-fim, .js-anexo-papel') : null;
            if (!input) return;
            const processoId = getProcessoId();
            if (!processoId) return;
            const anexoId = input.dataset.anexoId;
            const itemId = input.dataset.itemId;
            if (!anexoId || !itemId) return;

            // Card do anexo; reúne datas e papel deste anexo (salvos juntos para não perder o período)
            const container = input.closest('li') || document;
            const inputInicio = container.querySelector('.js-anexo-data-inicio[data-anexo-id="' + anexoId + '"]');
            const inputFim = container.querySelector('.js-anexo-data-fim[data-anexo-id="' + anexoId + '"]');
            const dataInicio = inputInicio ? inputInicio.value : '';
            const dataFim = inputFim ? inputFim.value : '';
            const papelSel = container.querySelector('.js-anexo-papel[data-anexo-id="' + anexoId + '"]:checked');
            const papel = papelSel ? papelSel.value : '';

            // Papel é obrigatório nos itens do Requisito V — marca visualmente quando ausente
            const papelGroup = container.querySelector('.rsc-anexo-papel[data-anexo-id="' + anexoId + '"]');
            if (papelGroup) papelGroup.classList.toggle('rsc-campo-invalido', !papel);

            // Atualiza o período localmente (mudança de papel não altera as datas, mas recomputar é inócuo)
            const periodoEl = document.querySelector('.js-periodo-display[data-anexo-id="' + anexoId + '"]');
            if (periodoEl) {
                periodoEl.textContent = calcularPeriodoDisplay(dataInicio, dataFim);
            }

            debounce(`anexo:${anexoId}`, 500, async () => {
                try {
                    const data = await salvarDatasAnexo(processoId, anexoId, dataInicio, dataFim, papel);
                    if (typeof data.pontuacao_total_item !== 'undefined') atualizarPontuacaoItem(itemId, data.pontuacao_total_item);
                    if (data.resumo) aplicarResumo(data.resumo);
                    if (periodoEl && data.periodo_display) {
                        periodoEl.textContent = data.periodo_display;
                    }
                } catch (e) {
                    console.error(e);
                }
            });
        });

        // Importante: não carregar anexos de todos os itens no page-load.
        // A página já vem renderizada pelo template; atualizamos a lista
        // apenas quando necessário (upload/exclusão).
    })();

    // ---------------------- Autosave do memorial (introdução / conclusão) ----------------------
    (function initMemorialAutosave() {
        const timers = {};
        document.addEventListener('input', (ev) => {
            const ta = ev.target && ev.target.closest ? ev.target.closest('.js-memorial-campo') : null;
            if (!ta) return;
            const processoId = getProcessoId();
            if (!processoId) return;
            const campo = ta.dataset.campo;
            const status = document.querySelector(`.js-memorial-status[data-campo="${campo}"]`);
            if (status) status.textContent = 'Salvando...';
            if (timers[campo]) clearTimeout(timers[campo]);
            timers[campo] = setTimeout(async () => {
                try {
                    const resp = await fetch(`/rsc_tae/processo/${processoId}/salvar_memorial/`, {
                        method: 'POST',
                        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: new URLSearchParams({ [campo]: ta.value, csrfmiddlewaretoken: getCsrfToken() }),
                    });
                    const data = await resp.json();
                    if (!data.ok) throw new Error(data.msg || 'Erro ao salvar');
                    ta.classList.toggle('rsc-campo-invalido', !ta.value.trim());
                    if (status) status.textContent = 'Salvo';
                } catch (e) {
                    console.error(e);
                    if (status) status.textContent = 'Erro ao salvar';
                }
            }, 600);
        });
    })();

    // ---------------------- Refresh de abas dinâmicas (Resumo / Memorial) ----------------------
    (function initAbasDinamicasRefresh() {
        const resumoContainer = document.getElementById('js-resumo-preenchimento');
        const memorialContainer = document.getElementById('js-memorial-descritivo');
        if (!resumoContainer && !memorialContainer) return;

        // Um controller por container, para abortar requisições concorrentes da mesma aba.
        const controllers = new WeakMap();

        async function refreshContainer(container, url, carregandoMsg, erroMsg) {
            if (!container) return;
            const processoId = getProcessoId();
            if (!processoId) return;

            const anterior = controllers.get(container);
            if (anterior) anterior.abort();
            const controller = new AbortController();
            controllers.set(container, controller);

            container.setAttribute('aria-busy', 'true');
            const prevHtml = container.innerHTML;
            container.innerHTML = `<p class="text-muted">${carregandoMsg}</p>`;

            try {
                const resp = await fetch(url.replace('{id}', processoId), {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    signal: controller.signal,
                });
                if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
                const data = await resp.json();
                if (!data.ok) throw new Error(data.msg || erroMsg);
                container.innerHTML = data.html || '';
            } catch (e) {
                if (e && e.name === 'AbortError') return;
                console.error(e);
                container.innerHTML = prevHtml;
            } finally {
                container.removeAttribute('aria-busy');
            }
        }

        function refreshResumo() {
            refreshContainer(resumoContainer, '/rsc_tae/processo/{id}/resumo_preenchimento/', 'Carregando resumo...', 'Erro ao carregar resumo');
        }

        function refreshMemorial() {
            refreshContainer(memorialContainer, '/rsc_tae/processo/{id}/memorial_descritivo/', 'Carregando memorial...', 'Erro ao carregar memorial');
        }

        function ensureFirstSubTab() {
            var content = document.querySelector('.rsc-requisito-tab-content');
            if (!content) return;
            if (content.querySelector('.rsc-requisito-pane.active')) return;
            var firstPane = content.querySelector('.rsc-requisito-pane');
            var firstBtn = document.querySelector('.rsc-requisito-tabs .nav-link');
            if (firstPane) firstPane.classList.add('active');
            if (firstBtn) {
                firstBtn.classList.add('active');
                firstBtn.setAttribute('aria-selected', 'true');
            }
        }

        const prevOnChangeTabs = window.onChangeTabs;
        window.onChangeTabs = function () {
            try {
                if (window.current_tab === 'formulario') {
                    ensureFirstSubTab();
                }
                if (window.current_tab === 'resumo-preenchimento') {
                    refreshResumo();
                }
                if (window.current_tab === 'memorial-descritivo') {
                    refreshMemorial();
                }
            } finally {
                if (typeof prevOnChangeTabs === 'function') prevOnChangeTabs();
            }
        };

        /* Sub-abas de requisitos (controle manual para não conflitar com djtools) */
        document.addEventListener('click', function (ev) {
            const btn = ev.target.closest('[data-rsc-tab]');
            if (!btn) return;
            ev.preventDefault();
            const container = btn.closest('.tab-pane, [data-tab]');
            if (!container) return;
            container.querySelectorAll('.rsc-requisito-tabs .nav-link').forEach(function (b) {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            container.querySelectorAll('.rsc-requisito-pane').forEach(function (p) {
                p.classList.remove('active');
            });
            var target = container.querySelector(btn.getAttribute('data-rsc-tab'));
            if (target) target.classList.add('active');
        });
    })();

    (function initIrParaItemNoFormulario() {
        function destacarLinhas(itemId) {
            const linhas = document.querySelectorAll(
                '.rsc-linha-principal[data-item-id="' + itemId + '"], .rsc-linha-anexos[data-item-id="' + itemId + '"]'
            );
            linhas.forEach(function (el) {
                el.classList.add('rsc-item-destacado');
                setTimeout(function () {
                    el.classList.remove('rsc-item-destacado');
                }, 2000);
            });
        }

        function irParaItem(itemId) {
            if (typeof changeTabs === 'function') changeTabs('formulario');

            const linhaPrincipal = document.querySelector('.rsc-linha-principal[data-item-id="' + itemId + '"]');
            if (!linhaPrincipal) return;

            const pane = linhaPrincipal.closest('.rsc-requisito-pane');
            if (pane) {
                const tabBtn = document.querySelector('.rsc-requisito-tabs .nav-link[data-rsc-tab="#' + pane.id + '"]');
                if (tabBtn) tabBtn.click();
            }

            requestAnimationFrame(function () {
                linhaPrincipal.scrollIntoView({ behavior: 'smooth', block: 'center' });
                destacarLinhas(itemId);
            });
        }

        document.addEventListener('click', function (ev) {
            const linha = ev.target.closest('.rsc-resumo-linha-problema[data-item-id]');
            if (!linha) return;
            ev.preventDefault();
            irParaItem(linha.dataset.itemId);
        });

        document.addEventListener('keydown', function (ev) {
            if (ev.key !== 'Enter' && ev.key !== ' ') return;
            const linha = ev.target.closest('.rsc-resumo-linha-problema[data-item-id]');
            if (!linha) return;
            ev.preventDefault();
            irParaItem(linha.dataset.itemId);
        });
    })();

    // ---------------------- Documentos preliminares ----------------------
    (function initDocumentosPreliminares() {
        const statusEl = document.getElementById('js-docs-preliminares-status');
        if (!statusEl) return; // aba sem permissão de edição — nada a fazer

        function setStatus(text) {
            statusEl.textContent = text || '';
        }

        function renderCard(tipo, documento) {
            const card = document.querySelector(`.js-doc-preliminar-card[data-tipo="${tipo}"]`);
            if (!card || !documento) return;

            // Badge de situação: após novo envio, sempre "Pendente".
            const situacaoEl = card.querySelector('.js-doc-preliminar-situacao');
            if (situacaoEl) {
                situacaoEl.className = 'status status-alert js-doc-preliminar-situacao';
                situacaoEl.textContent = documento.situacao_display || 'Pendente';
            }

            // Corpo: arquivo (link) + campo de data.
            const conteudo = card.querySelector('.js-doc-preliminar-conteudo');
            if (conteudo) {
                const arquivo = document.createElement('div');
                arquivo.className = 'rsc-doc-card__arquivo';
                const link = document.createElement('a');
                link.className = 'rsc-doc-card__arquivo-nome no-confirm';
                link.href = documento.url || '#';
                link.target = '_blank';
                link.rel = 'noopener';
                link.textContent = documento.nome || 'Arquivo';

                const label = document.createElement('label');
                label.className = 'rsc-doc-card__campo-data';
                const span = document.createElement('span');
                span.textContent = 'Data de obtenção/homologação:';
                const input = document.createElement('input');
                input.type = 'date';
                input.className = 'js-doc-preliminar-data rsc-data-input';
                input.dataset.documentoId = String(documento.id);
                input.value = documento.data_obtencao_titulacao || '';
                label.appendChild(span);
                label.appendChild(input);

                conteudo.innerHTML = '';
                conteudo.appendChild(arquivo);
                arquivo.appendChild(link);
                conteudo.appendChild(label);
            }

            // Footer: passa a "Substituir arquivo".
            const btn = card.querySelector('.js-doc-preliminar-selecionar');
            if (btn) {
                btn.innerHTML = '';
                btn.appendChild(document.createTextNode('Substituir arquivo'));
            }
        }

        // Selecionar arquivo: sobe imediatamente; a data é preenchida depois, no card.
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'application/pdf,.pdf';
        fileInput.style.display = 'none';
        document.body.appendChild(fileInput);

        let tipoAtual = null;

        document.addEventListener('click', function (ev) {
            const btn = ev.target.closest('.js-doc-preliminar-selecionar');
            if (!btn) return;
            tipoAtual = btn.dataset.tipo;
            fileInput.value = '';
            fileInput.click();
        });

        fileInput.addEventListener('change', async function () {
            const processoId = getProcessoId();
            const file = fileInput.files && fileInput.files[0];
            if (!processoId || !tipoAtual || !file) return;

            const url = `/rsc_tae/processo/${processoId}/documento_preliminar/upload/${tipoAtual}/`;
            const formData = new FormData();
            formData.append('arquivo', file);
            formData.append('csrfmiddlewaretoken', getCsrfToken());

            setStatus('Enviando...');
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData,
                });
                if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
                const data = await resp.json();
                if (!data.ok) throw new Error(data.msg || 'Erro ao enviar arquivo');

                renderCard(tipoAtual, data.documento);
                setStatus('Arquivo enviado');
                setTimeout(() => setStatus(''), 1500);
            } catch (e) {
                console.error(e);
                setStatus('Erro ao enviar arquivo');
            } finally {
                tipoAtual = null;
            }
        });

        // Autosave da data (por documento)
        async function salvarDataDocumento(processoId, documentoId, data) {
            const url = `/rsc_tae/processo/${processoId}/documento_preliminar/${documentoId}/salvar_data/`;
            const resp = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({ data_obtencao_titulacao: data || '', csrfmiddlewaretoken: getCsrfToken() }),
            });
            if (!resp.ok) throw new Error('Erro HTTP ' + resp.status);
            const json = await resp.json();
            if (!json.ok) throw new Error(json.msg || 'Erro ao salvar data');
            return json;
        }

        const debounceTimers = new Map();
        function debounce(key, ms, fn) {
            if (debounceTimers.has(key)) clearTimeout(debounceTimers.get(key));
            const t = setTimeout(function () {
                debounceTimers.delete(key);
                fn();
            }, ms);
            debounceTimers.set(key, t);
        }

        document.addEventListener('change', function (ev) {
            const input = ev.target.closest ? ev.target.closest('.js-doc-preliminar-data') : null;
            if (!input) return;
            const processoId = getProcessoId();
            const documentoId = input.dataset.documentoId;
            if (!processoId || !documentoId) return;

            debounce(`doc-data:${documentoId}`, 400, async function () {
                try {
                    setStatus('Salvando...');
                    await salvarDataDocumento(processoId, documentoId, input.value);
                    setStatus('Salvo');
                    setTimeout(() => setStatus(''), 1200);
                } catch (e) {
                    console.error(e);
                    setStatus('Erro ao salvar');
                }
            });
        });

        // Botão "Salvar" no rodapé: reforça o autosave de todas as datas visíveis, com feedback.
        const btnSalvar = document.getElementById('js-salvar-docs-preliminares');
        if (btnSalvar) {
            btnSalvar.addEventListener('click', async function () {
                const processoId = getProcessoId();
                if (!processoId) return;
                const inputs = document.querySelectorAll('.js-doc-preliminar-data');

                const semData = Array.from(inputs).filter((input) => !input.value);
                if (semData.length) {
                    semData.forEach((input) => input.reportValidity());
                    setStatus('Informe a data de obtenção/homologação de todos os documentos.');
                    return;
                }

                setStatus('Salvando...');
                try {
                    await Promise.all(
                        Array.from(inputs).map(function (input) {
                            const documentoId = input.dataset.documentoId;
                            if (!documentoId) return Promise.resolve();
                            return salvarDataDocumento(processoId, documentoId, input.value);
                        })
                    );
                    setStatus('Salvo com sucesso');
                    setTimeout(() => setStatus(''), 2000);
                } catch (e) {
                    console.error(e);
                    setStatus('Erro ao salvar');
                }
            });
        }
    })();
})();
