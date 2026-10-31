jQuery(document).ready(function(){

    var servidor = document.getElementsByName("servidor").item(0);
    var titular = document.getElementsByName("titular").item(0);

	function atualiza_valores(servidor){
        var servidor_id = servidor.value;
        if (!servidor_id){
            return;
        }

        $.ajax({
            url: "/calculos_pagamentos/get_valores/",
            data: {
                "id": servidor_id
            },
            method: "GET",
            dataType: 'json',
            success: function (data) {
                servidor.seta_valor(data);
            }
        });
    }

    function hide_show_docente(){
        $(".field-nivel").each(function() {
            $(this).show();
        });
        $(".field-padrao_vencimento_novo").each(function() {
            $(this).hide();
        });
        $(".field-titulacao_nova").each(function() {
            $(this).show();
        });
        $(".field-iq").each(function() {
            $(this).hide();
        });
        $(".field-titulacao").each(function() {
            $(this).show();
        });
    }

    function hide_show_tae(){
        $(".field-nivel").each(function() {
            $(this).hide();
        });
        $(".field-padrao_vencimento_novo").each(function() {
            $(this).show();
        });
        $(".field-titulacao_nova").each(function() {
            $(this).hide();
        });
        $(".field-iq").each(function() {
            $(this).show();
        });
        $(".field-titulacao").each(function() {
            $(this).hide();
        });
    }

    function filtra_niveis(nivel_string){
        $(".field-nivel_passado, .field-nivel").find("option").each(function() {
            if (this.innerHTML.indexOf(nivel_string) == -1 && this.innerHTML.indexOf("----") == -1){
                $(this).hide();
            }
            else{
                $(this).show();
            }

        });
    }

    function seta_valor_servidor(data){
        var vencimento = data.vencimento;
        var padrao = data.padrao;
        var jornada = data.jornada;
        var titulacao = data.titulacao;
        var nivel_string = data.nivel_string;

        filtra_niveis(nivel_string);

        if (vencimento){
            $('select[id$="-0-nivel"]').prop("value", vencimento);
        }
        // Abaixo atualiza se houver padrão e ñ for calculoprogressao, ou se for calculoprogressao sem portaria_id na URL
        if (padrao && (document.URL.indexOf("calculoprogressao") === -1 || document.URL.indexOf("portaria_id") === -1)){
            $('[id*="-0-padrao_vencimento_novo"]').prop("value", padrao);
        }
        if (jornada){
            $('select[id*="-0-jornada"]').last().val(jornada);
        }
        if (titulacao && nivel_string != "P"){
            $('[id*="-0-titulacao_nova"]').prop("value", titulacao);
        }
        if (nivel_string == "P"){
            hide_show_tae();
        }
        else{
            hide_show_docente();
        }

        // Cálculo de Substituição
        var funcao = data.funcao;
        var campus = data.campus;
        if (campus){
            jQuery('#id_campus').prop("value", campus);
        }
        if (funcao) {
            jQuery("#id_funcao_servidor_substituto").prop("value", funcao);
        }
    }

    function seta_valor_titular(data){
        var funcao = data.funcao;
        if (funcao) {
            jQuery("#id_funcao_servidor_titular").prop("value", funcao);
        }
    }

    servidor.seta_valor = seta_valor_servidor;
    if (titular) {
        titular.seta_valor = seta_valor_titular;
    }

    if (document.title.indexOf("Editar") == -1) { //Não vai atualizar automaticamente em tela de Edição
        $('select[name="servidor"]').change(
            function(){ 
                atualiza_valores(servidor);
            }
        );

        $('select[name="titular"]').change(
            function(){
                atualiza_valores(titular);
            }
        );
    }
    // IFMA/Tássio: Esconde/Mostra campos específicos dependendo do tipo de servidor
    if ($(".field-servidor").children().children(".filled").length>0 && $('[id*="-0-nivel"]').prop("value")) {
        if ($('[id*="-0-nivel"]')[0].innerHTML.indexOf('selected="">Técnico-Administrativo - P') >= 0) {
            hide_show_tae();
            nivel_string = "P";
        }
        else {
            hide_show_docente();
            if ($('[id*="-0-nivel"]')[0].innerHTML.indexOf('selected="">D') >= 0) {
                nivel_string = "D";
            }
            else{
                nivel_string = "-";
            }
        }
        filtra_niveis(nivel_string);
    }

});
