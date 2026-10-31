function check_tipo_resposta(){
	valor1 = $("#id_tipo_resposta").val();
	valor2 = $("#id_variavel_set-0-tipo").val();
	//numerico
    if (valor1 == 3 || valor1 == 4) {
        $(".form-row.field-escala").hide();
        $("#variavel_set-group").hide();
        $("#opcaoresposta_set-group").hide();
        $(".form-row.field-valor_minimo.field-valor_maximo").show();
        $(".form-row.field-formula").hide();
    //escolhas
    } else if (valor1 == 5 || valor1 == 6) {
        $(".form-row.field-escala").hide();
        $("#variavel_set-group").hide();
        $("#opcaoresposta_set-group").show();
        $(".form-row.field-valor_minimo.field-valor_maximo").hide();
        $(".form-row.field-formula").hide();
    //variaveis
    } else if (valor1 == 7) {
        $("#variavel_set-group").show();
        $("#opcaoresposta_set-group").hide();
        $(".form-row.field-valor_minimo.field-valor_maximo").hide();
        $(".form-row.field-formula").show();
    //Tratamento para uso de Escala Likert
    } else if (valor1 == 99) {
        $(".form-row.field-escala").show();
        $("#variavel_set-group").hide();
        $("#opcaoresposta_set-group").hide();
        $(".form-row.field-valor_minimo.field-valor_maximo").hide();
        $(".form-row.field-formula").hide();
    //texto
    } else {
        $(".form-row.field-escala").hide();
        $("#variavel_set-group").hide();
        $("#opcaoresposta_set-group").hide();
        $(".form-row.field-valor_minimo.field-valor_maximo").hide();
        $(".form-row.field-formula").hide();
    }
}

function check_respondentes_segmentos(element) {
    $("option[value!='']", element).attr('disabled', 'disabled');
    array_valores = $('#id_segmentos').val().split(';');

    jQuery.each(array_valores, function() {
        $("option[value='"+ this +"']", element).removeAttr('disabled');
    });
}

function check_segmento(select_segmento) {
    $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value!='']").attr('disabled', 'disabled');

    // CPA Central
    if ($(select_segmento).val() == 1) {
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Modalidade']").removeAttr('disabled');
    // CPA do Campus
    } else if ($(select_segmento).val() == 2) {
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Modalidade']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.CursoCampus']").removeAttr('disabled');
    // Gestor, Técnico ou Empresa
    } else if ($(select_segmento).val() == 3 || $(select_segmento).val() == 4 || $(select_segmento).val() == 11) {
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Modalidade']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select").val('edu.Modalidade');
    // ETEP
    } else if ($(select_segmento).val() == 5) {
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Modalidade']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Professor']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Turma']").removeAttr('disabled');
    // Docente
    } else if ($(select_segmento).val() == 6) {
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.CursoCampus']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Modalidade']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Turma']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select").val('edu.CursoCampus');
    // Estudante
    } else if ($(select_segmento).val() == 7) {
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.CursoCampus']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Professor']").removeAttr('disabled');
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.Turma']").removeAttr('disabled');
    // Evadido, Egresso
    } else if ($(select_segmento).val() == 8 || $(select_segmento).val() == 9) {
        $(select_segmento).parent().parent().parent().find(".field-objeto select[id^='id_iterador_set-'] option[value='edu.CursoCampus']").removeAttr('disabled');
    }
}

function init_check_segmento(){
    jQuery.each($(".field-segmento select[id^='id_iterador_set-']"), function(){
        check_segmento(this);
        check_respondentes_segmentos(this);
    });
}

$(document).ready(function(){
    $(".form-row.field-escala").hide();
    $("#variavel_set-group").hide();
    $("#opcaoresposta_set-group").hide();
    $(".form-row.field-valor_minimo.field-valor_maximo").hide();
    $(".form-row.field-formula").hide();

    $("#id_tipo_resposta").change(function(){
        check_tipo_resposta();
    });
    check_tipo_resposta();

    $('#iterador_set-group').delegate(".field-segmento select[id^='id_iterador_set-']", "focus", function() {
        check_respondentes_segmentos(this);
    });

    $('#iterador_set-group').delegate(".field-segmento select[id^='id_iterador_set-']", "change", function() {
        check_segmento(this);
    });
    init_check_segmento();


});
