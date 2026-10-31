// Replicando função URLQUERYSTRING até arranjar uma forma de importa-la de main.js
function URLQueryString(url) {
    this.url = String(url);
    this.querystringRegex = RegExp('[\?&]?([^&#=]*)=([^&#]*)*', 'g');
    let queryStringItens = [];
    let retorno;
    while ((retorno = this.querystringRegex.exec(this.url)) !== null) {
        let queryStringItem = {};
        queryStringItem[retorno[1]] = retorno[2];
        queryStringItens.push(queryStringItem);
    }
    this.queryStringItens = queryStringItens;
    this.get_string = function(string){
        return encodeURIComponent(string)
    };
    this.getQuerystringValue = function (name) {
        let queryStringItem = getQuerystringItem(name);
        return queryStringItem && queryStringItem[name]
    };
    this.getQuerystringItem = function (name) {
        return this.queryStringItens.filter(dict => dict[name])[0];
    };
    this.getQuerystringItens = function () {
        return this.queryStringItens;
    };
    this.delete = function (name) {
        this.queryStringItens = this.queryStringItens.filter(item => Object.keys(item) != name)
    };
    this.entries = function () {
        foo = {
            [Symbol.iterator]: () => ({
                items: this.queryStringItens.slice(),
                next: function next() {
                    return {
                        done: this.items.length === 0, // Vai nos dar true quando não houver mais itens
                        value: this.items.shift() // Remove o primeiro elemento da sequencia e retorna
                    }
                }
            })
        };
        return foo;
    };
    this.forEach = function (callback) {
        this.queryStringItens.forEach(callback);
    };
    this._getAllPair = function (name) {
        return this.queryStringItens.filter(item => Object.keys(item) == name);
    };
    this._getPair = function (name) {
        return this._getAllPair(name)[0] || null;
    };
    this.getAll = function (name) {
        return this._getAllPair(name).map(item => item[name]);
    };
    this.get = function (name) {
        return this._getPair(name)&&this._getPair(name)[name];
    };
    this.has = function (name) {
        return this.get(name) === null ? false : true;
    };
    this.keys = function () {
        return this.queryStringItens.map(item => Object.keys(item)[0]);
    };
    this.append = function (name, value) {
        let queryStringItem = {};
        queryStringItem[name] = value;
        this.queryStringItens.push(queryStringItem);
    };
    this.set = function (name, value) {
        let pairs = this._getAllPair(name);
        if (pairs){
            this.delete(name);
        }
        this.append(name, value);
    };
    this.sort = function () {
        this.queryStringItens.sort((x,y)=>Object.keys(x)>Object.keys(y)?1:-1);
    };
    this.toString = function () {
        return this.queryStringItens.map(item => Object.keys(item)+'='+Object.values(item)).join('&');
    };
    this.values = function () {
        return this.queryStringItens.map(item => Object.values(item)[0]);
    };
    this.isEmpty = function () {
        return this.values().length == 0;
    };
}

// A aba ativa fica em negrito; sem reserva ela alargava ao ser selecionada e empurrava as vizinhas. Cada texto solto da aba vai
// para um <span class="rotulo-aba" data-rotulo>, cuja cópia invisível em negrito (::after no tema) fixa a largura. Idempotente.
function reservarLarguraDoNegrito(contexto) {
    jQuery('.nav-tabs .nav-link', contexto || document).each(function () {
        jQuery(this).contents().filter(function () {
            return this.nodeType === Node.TEXT_NODE && this.textContent.trim() !== '';
        }).each(function () {
            jQuery(this).wrap(jQuery('<span class="rotulo-aba"></span>').attr('data-rotulo', this.textContent.trim()));
        });
    });
}
jQuery(function () { reservarLarguraDoNegrito(); });

// O Bootstrap 6 só registra o teclado (setas, Home, End) na instância da aba, e ela só nasce no clique, que o jQuery abaixo
// consome com `return false`. As instâncias são criadas aqui; o módulo do Bootstrap pode ainda não ter rodado.
function criarInstanciasDasAbas() {
    const criar = () => {
        document.querySelectorAll('.nav-tabs .nav-link[data-bs-toggle="tab"]').forEach(aba => window.bootstrap.Tab.getOrCreateInstance(aba));
    };
    if (window.bootstrap) {
        criar();
    } else {
        document.addEventListener('bootstrap:ready', criar, {once: true});
    }
}

// O clique o Bootstrap ativa sozinho (a data API dele roda na captura, antes do jQuery abaixo) e o jQuery faz o resto (conteúdo ajax,
// `?tab=`, `onChangeTabs`). A seta ativa pelo Bootstrap sem clique: nesse caso rodamos só os handlers jQuery do clique, sem
// despachar outro clique nativo (o navegador o descartaria) e sem cancelar o `show()`. `tabsPorTeclado` vale durante o keydown.
// `var` e não `let`: carregado duas vezes (o pipeline e um `{% javascript %}` avulso), o `let` de topo lançaria SyntaxError e derrubaria o script todo.
var tabsPorTeclado = false;
document.addEventListener('keydown', function (e) {
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) {
        tabsPorTeclado = true;
        setTimeout(() => { tabsPorTeclado = false; });
    }
}, true);
document.addEventListener('show.bs.tab', function (e) {
    if (tabsPorTeclado && e.target.matches('.nav-tabs .nav-link[data-tab]')) {
        jQuery(e.target).triggerHandler('click');
    }
});

initTabs = function(index) {
    // Cria o HTML para as abas
    let html = '<ul class="nav nav-tabs" role="tablist">';

    // Percorre todas as tabs para gerar as abas
    let active_tab = false;
    jQuery(".tab-pane:not([data-titled-tab=true])").each(function (idx) {
        let container = jQuery(this);
        let attr = "";
        let css_parent = "";
        let title = container.data("title");
        let tab_name = container.data("tab") || `tab${idx}`;
        let checked = container.data("checked");
        let counter = container.data("counter");
        let hide_tab = container.data("hide-tab-on-counter-zero");
        let info = container.data("tab-info");
        let public = container.data("public");
        let urlQueryString = new URLQueryString(window.location.search);
        let isActive = false;

        // Adiciona parametros do bootstrap à tab-pane
        container.addClass("fade").attr("role", "tabpanel").attr("id", tab_name + "-tab-pane");

        if (info) {
            css_parent += " tab-info";
        }
        if (public) {
            if (public === 'True') {
                css_parent += " tab-public";
                attr += ' title="Esta aba está visível publicamente."';
            } else {
                css_parent += " tab-not-public";
                attr += ' title="Esta aba não está visível publicamente."';
            }
        }
        
        if (urlQueryString.has('tab')) {
            if (urlQueryString.get('tab') == tab_name) {
                isActive = true;
                active_tab = tab_name;
            }
        } else {
            if (active_tab === false) {
                // Somente ativa a tab se não houver data-counter definido ou se o data-counter for maior que 0 ou se counter for 0 e hide-tab não estiver definido
                if (typeof counter === 'undefined' || counter > 0 || (counter === 0 && typeof hide_tab === 'undefined')) {
                    isActive = true;
                    active_tab = tab_name;
                }
            }
        }

        if (isActive) {
            container.addClass("active show");
        } else {
            container.removeClass("active show");
        }

        let checkedStatus = "";
        if (checked) {
            if (checked == "True" || checked == "true") {
                checkedStatus = " checked";
            } else {
                checkedStatus = " unchecked";
            }
        }
        if (counter == 0 && hide_tab === true) {
            attr += ' hidden';
        }
        // role="presentation": o <li> não pode virar listitem entre o tablist e a tab (WAI-ARIA tabs)
        html += '<li class="nav-item ' + css_parent + '" role="presentation" ' + attr + '>' +
            '<button type="button" class="nav-link' + (isActive ? ' active' : '') + checkedStatus + '" id="' + tab_name + '-tab" data-bs-target="#' + tab_name + '-tab-pane" data-tab="' + tab_name + '" data-bs-toggle="tab" role="tab" aria-controls="' + tab_name + '-tab-pane">' +
                title;
        if (counter > 0) {
            html += '<span class="badge">' + counter + '</span>';
        }
        html += '</button></li>';
    });
    html += '</ul>';

    // Insere as abas antes do .tab-content gerado
    let $tabPanes = jQuery(".tab-pane:not([data-titled-tab=true])");
    if (!$tabPanes.parent().hasClass("tab-content")) {
        $tabPanes.wrapAll('<div class="tab-content"></div>');
    }
    jQuery(html).insertBefore(".tab-content");

    changeTabs(active_tab, true);

    reservarLarguraDoNegrito();
    criarInstanciasDasAbas();

    // Ativa o clique para as abas
    jQuery('.nav-tabs .nav-link').click(function () {
        let tab = jQuery(this).data("tab");
        let url = '';
        let urlQueryString = new URLQueryString(window.location.search);
        urlQueryString.set('tab', tab);
        url = `?${urlQueryString.toString()}`;
        let item = jQuery(".tab-pane:not([data-titled-tab=true]):eq(" + tab + ")");
        history.pushState({}, '',url);
        if (isNaN(tab)) {
            item = jQuery(".tab-pane:not([data-titled-tab=true])[data-tab='" + tab + "']");
        }
        // Verifica se a origem do conteúdo, se ajax ou html
        if (item.length > 0){
            if (!item.html().trim()) {
                // Caso não tenha conteúdo HTML
                item.html("<p>Carregando....</p>");
                let cursor = document.body.style.cursor;
                jQuery("body").css('cursor', 'wait');
                jQuery.get(url, function (data) {
                    if (isNaN(tab)) {
                        var newTabContent = jQuery(".tab-pane:not([data-titled-tab=true])[data-tab='" + tab + "']", data).children(0);
                        var element = ".tab-pane:not([data-titled-tab=true])[data-tab='" + tab + "']";
                    } else {
                        var newTabContent = jQuery('.tab-pane:not([data-titled-tab=true]):eq(' + tab + ')', data).children(0);
                        var element = ".tab-pane:not([data-titled-tab=true]):eq(" + tab + ")";
                    }
                    jQuery(element).html(newTabContent);
                    changeTabs(tab);
                    if (typeof replaceAddAnotherLinks === 'function') replaceAddAnotherLinks();
                    initAll(element);
                    jQuery("body").css('cursor', cursor);
                });
            } else {
                changeTabs(tab);
            }
            return false;
        }
    });
    window.addEventListener("popstate", function (e) {
        if (window['changed_tab']) document.location.href = document.referrer;
    });
    onInitTabs = window['onInitTabs'];
    if (onInitTabs != null) onInitTabs();
}

// Mostra/Esconde divs de conteúdos e ativa/desativa abas
changeTabs = function(index, init=false) {
    window['changed_tab'] = true;
    window['current_tab'] = index;
    
    let tab_name = jQuery(this).data("tab");
    if (!tab_name) {
        tab_name = index;
    }
    
    jQuery(".pagination a").each(function () {
        if (tab_name){
            let urlQueryString = new URLQueryString(this.href.split('?')[1]);
            urlQueryString.set('tab', tab_name);
            this.href = `?${urlQueryString.toString()}`;
        }
    });
    if (!init) {
        // Chamadas diretas de changeTabs e `.trigger('click')` não passam pelo show() do Bootstrap: aria-selected e o tabindex
        // (rotativo) acompanham a aba ativa aqui. Só nas abas do tabs.js, não em `.nav-tabs` estáticos da página.
        jQuery(".nav-tabs .nav-link[data-tab]").removeClass('active').attr({'aria-selected': 'false', 'tabindex': -1});
        jQuery(".nav-tabs .nav-link[data-tab=" + index + "]").addClass('active').attr('aria-selected', 'true').removeAttr('tabindex');

        jQuery(".tab-pane:not([data-titled-tab=true])").removeClass('active show');
        if (isNaN(index)) {
            jQuery(".tab-pane:not([data-titled-tab=true])[data-tab='" + index + "']").addClass('active show');
        } else {
            jQuery(".tab-pane:not([data-titled-tab=true]):eq(" + index + ")").addClass('active show');
        }
    }

    onChangeTabs = window['onChangeTabs'];
    if (onChangeTabs != null) onChangeTabs();
    addTabParamToLinks();
}

addTabParamToLinks = function() {
    let aba_atual = $('.nav-link.active', '.nav-tabs').data('tab');
    let todos_nomes_tabs = [];
    // Percorrendo as abas para pegar os nomes
    jQuery('.tab-pane:not([data-titled-tab=true])').each(function () {
        todos_nomes_tabs.push(jQuery(this).data('tab'));
    });
    // Manipulando os links que possuem o parametro tab=
    jQuery("a[href*='tab=']:not('#breadcrumbs a')", "#content").each(function () {
        let href = jQuery(this).attr('href');
        if (/[?&]tab=$/.test(href) == true) {
            href = href.replace('tab=', 'tab=' + aba_atual);
        } else {
            jQuery.each(todos_nomes_tabs, function (index, value) {
                if (href.indexOf('tab=' + value) != -1) {
                    href = href.replace('tab=' + value, 'tab=' + aba_atual);
                }
            });
        }
        jQuery(this).attr('href', href);
    });
};

jQuery(function () {
    initTabs(0);
    window['changed_tab'] = false;
});
