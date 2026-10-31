/*
    saldo (informação contida e renderizada no form dinâmico através da variável 'info_saldo')
        data (aaaammdd)
        valor-em-segundos
        valor-distribuido-em-segundos
        valor-a-distribuir-em-segundos
        valor-distribuido-view
        valor-a-distribuir-view

    saldo saldo-externo (informação contida no form dinâmico através da variável 'infos_saldos_externos' e renderizada no template 'informar_compensacao_v2.html')
        saldo-externo-id
        valor-em-segundos
        valor-distribuido-em-segundos
        valor-a-distribuir-em-segundos
        valor-distribuido-view
        valor-a-distribuir-view

    debito (informação contida e renderizada no form dinâmico através da variável 'info_debito')
        data (aaaammdd)
        valor-em-segundos
        valor-compensado-em-segundos
        valor-compensado-view
        valor-restante-view

    saldo-utilizado (informação contida e renderizada no form dinâmico através da variável 'info_saldos_utilizados')
        valor-em-segundos
        valor-view
        é aqui onde está o informe de compensação:  
            1) input hidden name="datadebito__datasaldo" value="HH:MM:SS"
               ver método 'get_field_name' do form dinâmico
            2) input hidden name="datadebito__saldo_externo__saldoexternoid" value="HH:MM:SS"
                ver método 'get_field_name_saldo_externo' do form dinâmico

    saldo-totais (informação renderizada no template 'informar_compensacao_v2.html' e atualizada neste script através do método 'update_totais_saldos_debitos')
        saldo-total-view
        saldo-total-distribuido-view
        saldo-total-a-distribuir-view
 */

$(document).ready(function(){
    $("li.info").each(function () {
        if ($(this).html().length === 0)
            $(this).remove();
    });
    $("li.danger").each(function () {
        if ($(this).html().length === 0)
            $(this).remove();
    });

    $("a.visualizar-situacao-inicial").click(function(){
        visualizar_situacao_inicial();
    });
    $("a.redistribuir-saldo.sem-aproveitar-distribuicao").click(function(){
        redistribuir_saldos();
    });
    $("a.redistribuir-saldo.aproveitar-distribuicao").click(function(){
        redistribuir_saldos(true);
    });
});

function visualizar_situacao_inicial(){
    remover_saldos_utilizados();
    update_totais_saldos_debitos();

    $(".saldo").removeClass("saldo-arrastavel");
    $(".saldo").draggable('destroy');

    $(".debito").removeClass("debito-colavel");
    $(".debito").draggable('destroy');

    $(".help-auto-distribuicao").fadeOut("slow");
    $(".help-situacao-inicial").fadeIn("slow");
    $(".help-redistribuicao-saldos").fadeOut("slow");
}

function redistribuir_saldos(continuar_redistribuicao){
    if (continuar_redistribuicao === true)
        ativar_remocao_saldos_utilizados();
    else
        remover_saldos_utilizados();

    update_totais_saldos_debitos();
    $(".saldo").addClass("saldo-arrastavel");
    $(".debito").addClass("debito-colavel");

    set_eventos_arrastar_e_soltar_saldos();

    $(".help-auto-distribuicao").fadeOut("slow");
    $(".help-situacao-inicial").fadeOut("slow");
    $(".help-redistribuicao-saldos").fadeIn("slow");
}

function remover_saldo_utilizado(el_saldo_utilizado) {
    let valor_saldo_removido_em_segundos = parseInt($(el_saldo_utilizado).find(".valor-em-segundos").html());    
    let is_saldo_externo = $(el_saldo_utilizado).find("input").attr('name').indexOf('__saldo_externo__') >= 0;
    
    let data_saldo_correspondente;
    let saldo_externo_id_correspondente;

    if (is_saldo_externo) {
        saldo_externo_id_correspondente = $(el_saldo_utilizado).find("input").attr('name').split('__saldo_externo__')[1];  // int
    } else {
        data_saldo_correspondente = $(el_saldo_utilizado).find("input").attr('name').split('__')[1];  // aaaammdd
    }

    // atualiza total distribuído e total restante do saldo correspondente
    let el_saldo_correspondente = null;

    $(".saldo").each(function() {
        let el_saldo = this;
        
        let data_saldo = $(el_saldo).find(".data").html(); // aaaammdd
        let saldo_externo_id = $(el_saldo).find(".saldo-externo-id").html(); // int

        let el_saldo_match =
            (data_saldo && (data_saldo === data_saldo_correspondente)) || 
            (saldo_externo_id && (saldo_externo_id === saldo_externo_id_correspondente));
        
        if (el_saldo_match) {
            let valor_distribuido_em_segundos = parseInt($(el_saldo).find(".valor-distribuido-em-segundos").html());
            let novo_valor_distribuido = valor_distribuido_em_segundos - valor_saldo_removido_em_segundos;
            let valor_em_segundos = parseInt($(el_saldo).find(".valor-em-segundos").html());
            let novo_valor_a_distribuir = valor_em_segundos - novo_valor_distribuido;

            $(el_saldo).find(".valor-distribuido-em-segundos").html(novo_valor_distribuido);
            $(el_saldo).find(".valor-a-distribuir-em-segundos").html(novo_valor_a_distribuir);
            $(el_saldo).find(".valor-distribuido-view").html(formata_segundos(novo_valor_distribuido));
            
            if (novo_valor_distribuido != 0) {
                $(el_saldo).find(".valor-distribuido-view").parent("dd").parent("dl").removeClass("d-none");
            } else {
                $(el_saldo).find(".valor-distribuido-view").parent("dd").parent("dl").addClass("d-none");
            }
            
            $(el_saldo).find(".valor-a-distribuir-view").html(formata_segundos(novo_valor_a_distribuir));

            el_saldo_correspondente = el_saldo;

            return false;
        } 
    });

    $(el_saldo_utilizado).addClass("saldo-utilizado-remover");

    $(".saldo-utilizado-remover").removeClass("saldo-utilizado");
    $(".saldo-utilizado-remover").each(function(){
        $(this).slideUp("slow", function(){
            $(this).remove();
        });
    });

    update_totais_saldos_debitos();

    if (el_saldo_correspondente !== null){
        $(el_saldo_correspondente).fadeOut("slow", function () {
            $(this).show();
        })
    }
}

function remover_saldos_utilizados() {
    $(".saldo-utilizado").addClass("saldo-utilizado-remover");
    
    $(".saldo-utilizado-remover").removeClass("saldo-utilizado");
    $(".saldo-utilizado-remover").each(function(){
        $(this).slideUp("slow", function(){
            $(this).remove();
        });
    });
    
    $(".saldo").each(function(){
        let valor_em_segundos = parseInt($(this).find(".valor-em-segundos").html());

        $(this).find(".valor-distribuido-em-segundos").html(0);
        $(this).find(".valor-a-distribuir-em-segundos").html(valor_em_segundos);
        $(this).find(".valor-distribuido-view").html(formata_segundos(0));
        $(this).find(".valor-distribuido-view").parent("dd").parent("dl").addClass("d-none");        
        $(this).find(".valor-a-distribuir-view").fadeOut(function(){
            $(this).html(formata_segundos(valor_em_segundos));
            $(this).show();
        });
    });
    $(".saldo").parent().find(".saldo-totalmente-utilizado").hide();
}

function ativar_remocao_saldos_utilizados() {
    $(".saldo-utilizado").find("img.remover-saldo-utilizado").remove();
    $(".saldo-utilizado").find("p").prepend(
        "<img class='remover-saldo-utilizado' src='/static/admin/img/icon-deletelink.svg' title='Remover' style='float: right;'>"
    );
    set_eventos_remover_saldo_utilizado();
}

function update_totais_saldos_debitos() {
    /////////////////////////////
    // SALDOS
    let saldo_total = 0;
    let saldo_total_distribuido = 0;
    let saldo_total_a_distribuir = 0;

    $(".saldo").each(function(){
        let total_a_distribuir = parseInt($(this).find(".valor-a-distribuir-em-segundos").html());
        let eh_saldo_externo = $(this).hasClass("saldo-externo");

        saldo_total += parseInt($(this).find(".valor-em-segundos").html());
        saldo_total_distribuido += parseInt($(this).find(".valor-distribuido-em-segundos").html());
        saldo_total_a_distribuir += total_a_distribuir;

        // infos ref ao saldo (no final)
        $(this).parent().find(".info").each(function () {
            $(this).parent().append(this); // apenas "empurra" para o final
        });

        let el_msg_saldo_totalmente_utilizado = $(this).parent().find(".info.saldo-totalmente-utilizado");

        if (total_a_distribuir <= 0){
            $(this).parent().append(el_msg_saldo_totalmente_utilizado);  // será a última "na marra"
            
            $(el_msg_saldo_totalmente_utilizado).show();
            
            if (eh_saldo_externo) 
                $(this).parent().addClass("success").removeClass("warning");
            else
                $(this).addClass("success").removeClass("warning");
        } else {
            $(el_msg_saldo_totalmente_utilizado).hide();

            if (eh_saldo_externo) 
                $(this).parent().removeClass("success").addClass("warning");
            else
                $(this).removeClass("success").addClass("warning");
        }
    });

    $(".saldo-totais .saldo-total-view").fadeOut("slow", function(){
        $(this).html(formata_segundos(saldo_total));
        $(this).show();
    });

    $(".saldo-totais .saldo-total-distribuido-view").fadeOut("slow", function(){
        if (saldo_total_distribuido != 0) {
            $(this).addClass("true");
        } else {
            $(this).removeClass("true");
        }
        $(this).html(formata_segundos(saldo_total_distribuido));
        $(this).show();
    });

    $(".saldo-totais .saldo-total-a-distribuir-view").fadeOut("slow", function(){
        if (saldo_total_a_distribuir != 0) {
            $(this).addClass("false");
        } else {
            $(this).removeClass("false");
        }
        $(this).html(formata_segundos(saldo_total_a_distribuir));
        $(this).show();
    });

    /////////////////////////////
    // DÉBITOS
    let debito_total = 0;
    let debito_total_compensado = 0;

    $(".debito").each(function(){
        let valor_debito = parseInt($(this).find(".valor-em-segundos").html());
        let compensado = 0;

        $(this).parent().find(".saldo-utilizado").each(function(){
            compensado += parseInt($(this).find(".valor-em-segundos").html());
        });

        let valor_restante = valor_debito - compensado;
        if (valor_restante < 0)
            valor_restante = 0;

        $(this).find(".valor-compensado-em-segundos").html(compensado);

        if (compensado != 0) {
            $(this).find(".valor-compensado-view").parent("dd").parent("dl").removeClass("d-none")
        } else {
            $(this).find(".valor-compensado-view").parent("dd").parent("dl").addClass("d-none");
        }

        $(this).find(".valor-compensado-view").html(formata_segundos(compensado));
        $(this).find(".valor-restante-view").html(formata_segundos(valor_restante));

        // infos ref ao débito (no final)
        $(this).parent().find(".info").each(function () {
            $(this).parent().append(this); // apenas "empurra" para o final
        });

        let el_msg_debito_totalmente_compensado = $(this).parent().find(".info.debito-totalmente-compensado");
        if (valor_debito - compensado <= 0){
            $(this).parent().append(el_msg_debito_totalmente_compensado);  // será a última "na marra"
            $(el_msg_debito_totalmente_compensado).show();
            $(this).addClass("success").removeClass("danger");
        } else {
            $(el_msg_debito_totalmente_compensado).hide();
            $(this).removeClass("success").addClass("danger");
        }

        debito_total += valor_debito;
        debito_total_compensado += compensado;
    });

    let debito_total_restante = debito_total - debito_total_compensado;
    if (debito_total_restante < 0)
        debito_total_restante = 0;

    $(".saldo-totais .debito-total-view").fadeOut("slow", function(){
        $(this).html(formata_segundos(debito_total));
        $(this).show();
    });

    $(".saldo-totais .debito-total-restante-view").fadeOut("slow", function(){
        if (debito_total_restante != 0) {
            $(this).addClass("false");
        } else {
            $(this).removeClass("false");
        }
        $(this).html(formata_segundos(debito_total_restante));
        $(this).show();
    });
}

function set_eventos_arrastar_e_soltar_saldos(){
    $(".saldo-arrastavel").draggable({
        cursor: "move",
        cursorAt: { top: 0, left: 0 },
        opacity: 0.9,
        revert: "invalid",
        helper: function(event) {
            let el_saldo = this;
            let data_saldo = $(el_saldo).find(".data").html(); // aaaammdd
            let saldo_externo_id = $(el_saldo).find(".saldo-externo-id").html(); // int
            
            let el_saldo_clone = $("<div>?</div>");

            if (data_saldo)
                el_saldo_clone = $(el_saldo).clone().addClass('saldo-arrastando');
            else if (saldo_externo_id)
                el_saldo_clone = $(el_saldo).parent().clone().addClass('saldo-externo-arrastando');
            
            return el_saldo_clone;
        },
        start: function(event, ui) {
            let data_saldo = $(ui.helper).find(".data").html(); // aaaammdd
            let saldo_externo_id = $(ui.helper).find(".saldo-externo-id").html(); // int

            if (data_saldo) {
                let data_saldo_em_d_m_a = get_dia_mes_ano(data_saldo);                
                $(ui.helper).prepend(`<strong>${data_saldo_em_d_m_a[0]}/${data_saldo_em_d_m_a[1]}/${data_saldo_em_d_m_a[2]}</strong><div class='clear'/>`);
            } else if (saldo_externo_id) {
                $(ui.helper).prepend("<strong>Saldo Externo</strong><div class='clear'/>");
            }
        },
        drag: function(event, ui) {
            $(ui.helper).css("width", $(ui.helper.context).css("width"));
            $(ui.helper).css("border", "1px dashed #000");
        },
        stop: function(event, ui) {
        }
    });

    $(".debito-colavel").droppable({
        greedy: true,  // não propaga para os parents
        tolerance: "pointer", // a ponta do mouse
        over: function(event, ui) { // sobrevoando o débito ...
            let el_debito = this;
            let el_saldo = ui.draggable;

            if (is_pode_soltar_saldo(el_saldo, el_debito)){
                $(el_debito).addClass("debito-pode-utilizar-o-saldo");
            }
        },
        out: function(event, ui) { // saindo de cima do débito, sem soltar ...
            let el_debito = this;
            $(el_debito).removeClass("debito-pode-utilizar-o-saldo");
        },
        drop: function(event, ui) { // soltando em cima do débito ...
            let el_debito = this;
            let el_saldo = ui.draggable;
            
            $(ui.helper).remove();

            $(el_debito).removeClass("debito-pode-utilizar-o-saldo");

            if (is_pode_soltar_saldo(el_saldo, el_debito)){
                let data_debito = $(el_debito).find(".data").html(); // aaaammdd
                let data_saldo = $(el_saldo).find(".data").html(); // aaaammdd
                let saldo_externo_id = $(el_saldo).find(".saldo-externo-id").html(); // int

                let valor_debito = parseInt($(el_debito).find(".valor-em-segundos").html());
                let valor_debito_compensado = parseInt($(el_debito).find(".valor-compensado-em-segundos").html());
                let valor_debito_restante = valor_debito - valor_debito_compensado;
                let valor_saldo_restante = parseInt($(el_saldo).find(".valor-a-distribuir-em-segundos").html());

                let valor_utilizado_pelo_debito = valor_debito_restante;
                
                if (valor_saldo_restante < valor_debito_restante)
                    valor_utilizado_pelo_debito = valor_saldo_restante;

                let valor_utilizado_pelo_debito_em_h_m_s = get_hora_min_seg(valor_utilizado_pelo_debito);                
                let info_saldo;
                let input_name;
                
                if (data_saldo) {
                    info_saldo = get_dia_mes_ano(data_saldo);
                    input_name = data_debito + "__" + data_saldo; // aaaammdd__aaaammdd
                } else if (saldo_externo_id) {
                    info_saldo = "Saldo Externo #" + saldo_externo_id;
                    input_name = data_debito + "__saldo_externo__" + saldo_externo_id; // aaaammdd__saldo_externo__id
                }

                // insere um elemento "saldo-utilizado", incluindo o field input do informe de compensação
                $(el_debito).parent().append("" +
                    "<li class='extra saldo-utilizado'>" +
                        "<span class='valor-em-segundos' hidden='hidden'>" + valor_utilizado_pelo_debito + "</span>" +
                        "<p>" +
                            "<img class='remover-saldo-utilizado' src='/static/admin/img/icon-deletelink.svg' title='Remover' style='float: right;'>" +
                                "Saldo utilizado: <strong>" +
                                    "<span class='valor-view'>" + formata_segundos(valor_utilizado_pelo_debito) + "</span>" +
                                "</strong> " +
                                "(" + info_saldo + ")." +
                        "</p>" +
                        "<input type='hidden' " +
                        "       name='" + input_name + "' " +
                        "       value='" + valor_utilizado_pelo_debito_em_h_m_s[0] + ":" + valor_utilizado_pelo_debito_em_h_m_s[1] + ":" + valor_utilizado_pelo_debito_em_h_m_s[2] +"'/>" +
                    "</li>");

                let saldo_valor_total = parseInt($(el_saldo).find(".valor-em-segundos").html());
                let saldo_valor_distribuido = parseInt($(el_saldo).find(".valor-distribuido-em-segundos").html()) + valor_utilizado_pelo_debito;
                let saldo_valor_a_distribuir = saldo_valor_total - saldo_valor_distribuido;
                
                $(el_saldo).find(".valor-distribuido-em-segundos").html(saldo_valor_distribuido);
                $(el_saldo).find(".valor-a-distribuir-em-segundos").html(saldo_valor_a_distribuir);
                $(el_saldo).find(".valor-distribuido-view").html(formata_segundos(saldo_valor_distribuido));
                
                if (saldo_valor_distribuido != 0) {
                    $(el_saldo).find(".valor-distribuido-view").parent("dd").parent("dl").removeClass("d-none");
                } else {
                    $(el_saldo).find(".valor-distribuido-view").parent("dd").parent("dl").addClass("d-none");
                }
                
                $(el_saldo).find(".valor-a-distribuir-view").html(formata_segundos(saldo_valor_a_distribuir));

                set_eventos_remover_saldo_utilizado();

                update_totais_saldos_debitos();
            }
        }
    });
}

function set_eventos_remover_saldo_utilizado() {
    $(".remover-saldo-utilizado").off('click');
    $(".remover-saldo-utilizado").on('click', function(){
        let el_saldo_utilizado = $(this).parent().parent();
        remover_saldo_utilizado(el_saldo_utilizado);
    });
}

function is_pode_soltar_saldo(el_saldo, el_debito){
    let valor_debito = parseInt($(el_debito).find(".valor-em-segundos").html());
    let valor_debito_compensado = parseInt($(el_debito).find(".valor-compensado-em-segundos").html());
    let valor_debito_restante = valor_debito - valor_debito_compensado;
    let valor_saldo_restante = parseInt($(el_saldo).find(".valor-a-distribuir-em-segundos").html());

    // deve haver saldo disponível e débito a compensar
    return valor_saldo_restante > 0 && valor_debito_restante > 0;
}
