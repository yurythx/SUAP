class RegiaoIndex {
    constructor() {
        this.numElementos = 0;
        this.carregado = this.carregado.bind(this);
        this.elementos = this.montarElementos();
    }

    carregado() {
        this.numElementos++;

        if (this.numElementos === this.elementos.length) {
            this.postCarreado();
        }
    }    

    carregar() {
        for (const elemento of this.elementos) {
            elemento.carregar();
        }
    }
}

// Tratamento das colunas de quadros
// #region quadros
class Quadro {
    constructor(coluna, callback) {
        this.coluna = coluna;
        this.callback = callback;
        this.url = `/comum/index/meus_quadros_por_coluna/${coluna}/`;
    }

    carregar() {
        let skeleton = `.coluna-${this.coluna} .skeleton`;
        let content = `.coluna-${this.coluna} .content`;
                
        $(skeleton).show();

        $.ajax({
            type: "GET",
            url: this.url,
        }).done((data) => {
            $(skeleton).hide();
            $(`.coluna-${this.coluna}`).append(data);
            this.callback();
        }).fail((data) => {
            $(skeleton).hide();
            $(content).html('<p class="false">Erro ao baixar dados. Recarregue esta página novamente.</p>');
        });
    }
}

class QuadrosIndex extends RegiaoIndex{
    constructor () {
        super();
    }

    montarElementos() {
        return [
            new Quadro('esquerda', this.carregado),
            new Quadro('centro', this.carregado),
            new Quadro('direita', this.carregado)
        ];
    }

    postCarreado() {
        this.sorteavel();
        this.esconderQuadro();
        this.marcarQuadroComoLido();
    }

    sorteavel() {
        // jQuery-UI (sortable) pode não ter carregado em conexões instáveis (mobile);
        // sem este guard a chamada estoura "sortable is not a function" (Sentry SUAP-TB0).
        // Sem ordenação por arrastar a página segue funcional.
        if (typeof $.fn.sortable !== 'function') {
            return;
        }
        $(".coluna").sortable({
            connectWith: ".coluna",
            handle: ".portlet-header",
            cancel: ".portlet-toggle",
            placeholder: "portlet-placeholder ui-corner-all",
            beforeStop: function( event, ui ) {
                let item = ui.item[0];
                let coluna = '3';
                let cont_item = $(item).prevAll().length;

                if ($(item.parentElement).hasClass('coluna-esquerda')) {
                    coluna = '1';
                } else {
                    if ($(item.parentElement).hasClass('coluna-centro')) {
                        coluna = '2';
                    }
                }

                $.ajax({
                    type: "POST",
                    url: "/comum/index/layout/",
                    data: {
                        titulo: $(item).find('.portlet-header').find('.titulo')[0].getAttribute("data-quadro"), 
                        coluna: coluna, 
                        ordem: cont_item
                    }
                });
            }
        });
        $(document).on('click', ".reposicionar-quadro", function(){
            $(this).closest('.modulo-info').toggleClass('ui-sortable-helper');
        });
    }

    esconderQuadro() {
        $(".esconder-quadro").on('click', function(){
            $.ajax({
                type: "POST",
                url: "/comum/index/esconder_quadro/",
                data: {titulo: $(this).data('quadro')}
            });
            $(this).closest('.modulo-info').hide();
        });
    }

    marcarQuadroComoLido() {
        $(".marcar-quadro-como-lido").on('click', function(){
            $.ajax({
                type: "POST",
                url: `/comum/index/marcar_quadro_como_lido/${$(this).data('hash')}/`,
                data: {titulo: $(this).data('quadro')}
            });
            $(this).closest('.modulo-info').hide();
        });
    }
}
// #endregion

// Tratamento dos avisos
// #region avisos
class Alerta {
    constructor(classe, url, callback) {
        this.classe = classe;
        this.url = url;
        this.callback = callback;

        $(document).on('click', `${this.classe} button.dropdown-item`, () => {
            this.carregar();
        });
    }

    carregar() {
        let skeleton = `${this.classe} .skeleton`;
        let content = `${this.classe} .content`;

        $(skeleton).show();
        $(content).hide();

        $.ajax({
            type: "GET",
            url: this.url,
        }).done((data) => {
            $(skeleton).hide();
            if (!data || !data.trim()) {
                $(this.classe).remove();
            } else {
                $(content).html(data);
                $(content).show();
            }
        }).fail((data) => {
            $(skeleton).hide();
            $(content).html('<h4 class="false">Erro ao baixar dados. Recarregue esta página novamente.</h4>');
        }).always(() => {
            this.callback();
        });
    }

    temDados() {
        const content = $(`${this.classe} .content`);

        if (content.length === 0) {
            return false;
        }

        const html = content.html();
        return html && html.trim() !== '';
    }
}

class AlertasIndex extends RegiaoIndex{
    constructor () {
        super();
    }

    montarElementos() {
        return [
            new Alerta('.avisos', '/comum/index/meus_avisos/', this.carregado),
            new Alerta('.fique-atento', '/comum/index/meus_alertas/', this.carregado),
            new Alerta('.pendencias', '/comum/index/minhas_pendencias/', this.carregado),
            new Alerta('.pendencias_coletivas', '/comum/index/minhas_pendencias_coletivas/', this.carregado)
        ];
    }
    
    postCarreado() {
        if (this.elementos.every(valor => valor.temDados() === false)) {
            $("body").removeClass("hasAsideLeft");
            $(".alertas").hide();
        } else {
            $("body").addClass("hasAsideLeft");
            $(".alertas .content").show();
        }
    }
}
// #endregion

const carregarPainelControleSecretarioAcademico = () => {
    $.ajax({
    type: "GET",
    url: `/comum/index/painel_controle_secretario_academico/${window.location.search}`
    }).done((data) => {
        if (data.trim()){
            $(`[id='painel-controle-secretario-academico']`).html(data);
        } else {
            $(`[id='painel-controle-secretario-academico']`).hide();
        }
    });
}
