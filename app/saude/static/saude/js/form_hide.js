$(document).ready(function () {
    exibir_esconder_campo();
    $("#id_perda_peso").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_ganho_peso").on('change', function () {
        exibir_esconder_campo();
    });


    $("#id_alergia_alimentos").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_doencas_previas").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_alergia_medicamentos").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_usa_medicamentos").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_transtorno_psiquiatrico").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_psiquiatra").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_lesoes_ortopedicas").on('change', function () {
        exibir_esconder_campo();
    });



    $("#id_problema_auditivo").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_problema_aprendizado").on('change', function () {
        exibir_esconder_campo();
    });



    $("#id_vida_sexual_ativa").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_foi_dentista_anteriormente").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldades").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_uso_internet").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_motivo_chegada").on('change', function () {
        exibir_esconder_campo();
    });

    $("input[type='checkbox']").click(function () {
        exibir_esconder_campo();
    });

});


function exibir_esconder_campo() {
    // Antropometria
    if ($('#id_perda_peso').is(':checked')) {
        $('#id_quanto_perdeu').parent().parent().show();
    } else {
        $('#id_quanto_perdeu').parent().parent().hide();
    }
    if ($('#id_ganho_peso').is(':checked')) {
        $('#id_quanto_ganhou').parent().parent().show();
    } else {
        $('#id_quanto_ganhou').parent().parent().hide();
    }

    // DesenvolvimentoPessoal
    if ($('#id_problema_auditivo').is(':checked')) {
        $('#id_qual_problema').parent().show();
    } else {
        $('#id_qual_problema').parent().hide();
    }
    if ($('#id_problema_aprendizado').val() == 'True') {
        $('#id_qual_problema_aprendizado').parent().show();
        $('#id_origem_problema').parent().show();
        $("#id_qual_problema_aprendizado").parent().addClass('required');
        $("#id_origem_problema").parent().addClass('required');
    } else {
        $('#id_qual_problema_aprendizado').parent().hide();
        $('#id_origem_problema').parent().hide();
        $("#id_qual_problema_aprendizado").val('');
        $("#id_qual_problema_aprendizado").parent().removeClass('required');
        $("#id_origem_problema").val('');
        $("#id_origem_problema").parent().removeClass('required');
    }

    if ($('#id_motivo_chegada').val() == 7) {
        $('#id_descricao_encaminhamento_externo').parent().parent().show();

    }
    else {
        $('#id_descricao_encaminhamento_externo').parent().parent().hide();
        $('#id_descricao_encaminhamento_externo').val('');

    }


    var valores_marcados = [];
    $('input:checkbox[name=queixa_principal]:checked').each(function () {
        valores_marcados.push($(this).val());
    });
    if (valores_marcados.includes('24')) {
        $('#id_descricao_queixa_outros').parent().parent().show();
    } else {
        $('#id_descricao_queixa_outros').parent().parent().hide();
    }


    var valores_marcados = [];
    $('input:checkbox[name=queixa_identificada]:checked').each(function () {
        valores_marcados.push($(this).val());
    });
    if (valores_marcados.includes('24')) {
        $('#id_descricao_queixa_identificada_outros').parent().parent().show();
    } else {
        $('#id_descricao_queixa_identificada_outros').parent().parent().hide();
    }
}
