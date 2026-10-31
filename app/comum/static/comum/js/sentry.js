// Configuração do Sentry JS (frontend) do SUAP.
//
// Os valores dinâmicos (versão, ambiente, nome do servidor) chegam via o global
// window.__SENTRY_SUAP__, injetado inline pelo template admin/sentry.html. Tudo
// que é estático (ignoreErrors/denyUrls/beforeSend) vive aqui para ser minificado
// pelo django-pipeline (bundle 'sentry') e cacheado pelo navegador.
//
// Definir sentryOnLoad ANTES do Loader Script do Sentry (admin/sentry.html garante
// a ordem: este arquivo carrega antes do loader).
window.sentryOnLoad = function () {
    var cfg = window.__SENTRY_SUAP__ || {};
    Sentry.init({
        release: cfg.release,
        environment: cfg.environment,
        // Erros opacos "Script error." vêm de scripts cross-origin de terceiros
        // (extensões/WebView no iOS Safari), mascarados pelo navegador na origem.
        // Não são código do SUAP e não há stack a recuperar: ruído inacionável.
        // Os demais padrões cobrem mensagens lançadas por extensões (MetaMask,
        // carteiras cripto, antivírus) que se injetam na página.
        ignoreErrors: [
            'Script error.',
            'Failed to connect to MetaMask',
            'MetaMask extension not found',
            /MetaMask/i,
            /ethereum/i,
            // Navegadores in-app (Google/Instagram/etc.) e o app iOS injetam
            // pontes nativas em window.webkit.messageHandlers; quando o Highcharts
            // chama window.print() num WebView sem a ponte, estoura. É ambiente do
            // usuário, não código do SUAP — ruído inacionável.
            /window\.webkit\.messageHandlers/i,
            // fancybox dispara "reading 'opts'" a partir de handlers anônimos
            // (jQuery minificado inline), cujo frame de topo é a própria página
            // — o denyUrls de /fancybox.js não alcança. Ruído interno da lib.
            // As três variantes são a mesma falha em Chrome/Firefox/Safari
            // (Sentry SUAP-TAY/TNC/TF1).
            /Cannot read properties of undefined \(reading 'opts'\)/,
            /can't access property "opts", current is undefined/,
            /evaluating 'current\.opts'/,
            // window.setDgResult não existe no SUAP: é injetado por WebView/app
            // mobile que espera um callback nosso. Contrato de terceiro, não é
            // código do SUAP (Sentry SUAP-TA9).
            /setDgResult is not a function/,
            // Globais first-party (jQuery/$, initAll, open_menu_item,
            // QuadrosIndex, AlertasIndex, goToPageTop,
            // AtualizarContadorNotificacoesNaoLidas — todos em main.js) e libs
            // vendorizadas (tinymce, Highcharts via CDN) só ficam indefinidos
            // quando o bundle JS não baixa — falha transitória de rede em
            // clientes mobile. Os scripts são síncronos no <head>, então em rede
            // normal sempre carregam antes do uso; a página já está quebrada
            // nesse cliente e o erro é inacionável em código (Sentry
            // SUAP-TAR/TA4/V3H/TAF/V3A/V37/TA5/TG5/TNN). Um erro real de ordenação
            // apareceria em toda carga (dev/desktop) e seria pego antes de produção.
            /(jQuery|\$|initAll|open_menu_item|QuadrosIndex|AlertasIndex|tinymce|tinyMCE|Highcharts|goToPageTop|AtualizarContadorNotificacoesNaoLidas) is not defined/,
            /Can't find variable: (\$|jQuery|initAll|open_menu_item|QuadrosIndex|AlertasIndex|tinymce|tinyMCE|Highcharts|goToPageTop|AtualizarContadorNotificacoesNaoLidas)/,
            // maskedinput.js faz `$.maskWatchers = {}` no carregamento; quando o
            // jQuery não baixou, `$` é undefined e o set estoura. Mesma falha de
            // carregamento da lista acima; cobre as duas frases Chrome/Safari
            // (Sentry SUAP-TE3/TM7).
            /maskWatchers/,
            // ServiceWorkerRegistration falha quando o documento está sendo
            // descarregado (navegação/refresh): estado do navegador, não código
            // do SUAP — inacionável (Sentry SUAP-TED).
            /Failed to get ServiceWorkerRegistration/,
            // localStorage cheio: o tinymce (autosave/cores) e outros estouram a
            // cota do navegador do usuário. Ambiente do cliente, inacionável
            // (Sentry SUAP-V3Y/V3K/V4X).
            /QuotaExceededError/,
            // runtime.sendMessage é API de extensão de navegador injetada na
            // página; "Tab not found" é a extensão do usuário, não o SUAP
            // (Sentry SUAP-TCB).
            /runtime\.sendMessage/,
            // "ResizeObserver loop ..." é um aviso benigno do próprio navegador
            // (reflow adiado p/ o próximo frame), não um erro do SUAP. Ruído
            // reconhecidamente inacionável (Sentry SUAP-TM0).
            /ResizeObserver loop/,
        ],
        // Descarta eventos cujo frame de topo do stack vem de uma extensão de
        // navegador (chrome-extension://, moz-extension://, etc.). Não é código
        // do SUAP: ruído inacionável injetado pelo browser do usuário.
        denyUrls: [
            /extensions\//i,
            /^chrome:\/\//i,
            /^chrome-extension:\/\//i,
            /^moz-extension:\/\//i,
            /^safari-extension:\/\//i,
            /^safari-web-extension:\/\//i,
            // Bibliotecas de terceiros vendorizadas em /static/. O denyUrls casa
            // só o frame de TOPO do stack, então descarta apenas erros lançados
            // DENTRO da lib (ruído interno inacionável: fancybox current.opts,
            // Highcharts #13/addEvent, CKEditor isContentEditable). Bugs de uso
            // do SUAP estouram no call site (frame da página) e seguem visíveis.
            // Padrões ancorados no nome do arquivo p/ não pegar a cola do SUAP
            // (ckeditor-init.js, init_tinymce.js, ckeditor_toolbar.js) nem futuros.
            /\/fancybox(-core)?\.js/i,
            /\/(highcharts|exporting)\.js/i,
            /\/ckeditor\/ckeditor\/ckeditor\.js/i,
            /\/select2\.js/i,
            /\/tinymce(\.min)?\.js/i,
            // Plugins internos do tinymce (autosave isEmpty, help i18n que falha
            // ao baixar): ruído da lib, não da cola do SUAP em /tinymce/
            // tiny_mce_toolbar.js (que NÃO casa este padrão /plugins/). (Sentry
            // SUAP-V3M/V4C/V3B)
            /\/tinymce\/plugins\//i,
            // Código de extensão Safari mascarado pelo navegador; não é do SUAP
            // (Sentry SUAP-TDK).
            /webkit-masked-url/i,
        ],
        beforeSend: function (event) {
            try {
                var values = event.exception && event.exception.values;
                var ehSyntaxError = values && values.some(function (v) { return v.type === 'SyntaxError'; });
                var url = (event.request && event.request.url) || '';
                // SyntaxError sem nenhum frame ("Unexpected end of input"/"Unexpected
                // token") aparece sitewide em dezenas de URLs (Sentry SUAP-TCA): é
                // script inline injetado por extensão/WebView, fora do código do SUAP
                // e impossível de localizar (stackless). Mesma classe do PDF embutido
                // em /avaliar_item_arquivo/<id>/ (Sentry SUAP-V01… cluster). Dropar é
                // seguro: um SyntaxError inline REAL do SUAP apareceria em toda carga
                // (dev/desktop) e num único bucket, não disperso por URL.
                var semStack = values && values.every(function (v) {
                    return !v.stacktrace || !v.stacktrace.frames || v.stacktrace.frames.length === 0;
                });
                if (ehSyntaxError && (semStack || url.indexOf('/avaliar_item_arquivo/') !== -1)) {
                    return null;
                }
            } catch (e) {
                // nunca bloquear o envio por falha no próprio filtro
            }
            return event;
        },
    });
    Sentry.setTag('suap.server.name', cfg.serverName);
};
