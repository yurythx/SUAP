$(document).ready(function(){
    exibir_esconder_campo();
    $("#id_fez_cirurgia").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_hemorragia").on('change', function () {
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

    $("#id_doencas_previas").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_problema_auditivo").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_tem_deficiencia").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_tem_transtorno_neuro").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_tem_acompanhamento_transtorno_neuro").on('change', function () {
        exibir_esconder_campo();
    });

     $("#id_tem_doenca_cronica").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='doencas_cronicas']").on('change', function () {
        exibir_esconder_campo();
    });

   $("#id_usa_aparelho_auditivo").on('change', function () {
        exibir_esconder_campo();
    });

})

function clearAlergiaMedicamentos() {
    $("select[name='grupos_medicamentos']").val(null).trigger('change');
}

function clearDoencasCronicas() {
    $("select[name='doencas_cronicas']").val(null).trigger('change');
}

function clearTranstornos() {
    $("select[name='quais_transtornos_neuro']").val(null).trigger('change');
}

function exibir_esconder_campo() {
    if ($('#id_fez_cirurgia').val() == 'True') {
        $('#id_que_cirurgia').parent().parent().show();
        $("#id_que_cirurgia").parent().addClass('required');
        $("#id_tempo_cirurgia").parent().addClass('required');
    } else {
        $('#id_que_cirurgia').parent().parent().hide();
        $("#id_que_cirurgia").val('');
        $("#id_que_cirurgia").parent().removeClass('required');
        $("#id_tempo_cirurgia").val('');
        $("#id_tempo_cirurgia").parent().removeClass('required');
    }
    if ($('#id_hemorragia').val() == 'True') {
        $('#id_tempo_hemorragia').parent().show();
        $("#id_tempo_hemorragia").parent().addClass('required');
        $('#id_descricao_hemorragia').parent().show();
        $("#id_descricao_hemorragia").parent().addClass('required');

    } else {
        $('#id_tempo_hemorragia').parent().hide();
        $("#id_tempo_hemorragia").val('');
        $("#id_tempo_hemorragia").parent().removeClass('required');
        $("#id_descricao_hemorragia").parent().hide();
        $("#id_descricao_hemorragia").val('');
        $("#id_descricao_hemorragia").parent().removeClass('required');
    }

    if ($('#id_alergia_medicamentos').val() == 'True') {
        $('#id_que_medicamentos').parent().show();
        $("#id_que_medicamentos").parent().addClass('required');
        $("select[name='grupos_medicamentos']").parent().parent().show();
        $("select[name='grupos_medicamentos']").parent().addClass('required');
        $('#id_efeitos_adversos_medicamentos').parent().show();
        $("#id_efeitos_adversos_medicamentos").parent().addClass('required');


    } else {
        $('#id_que_medicamentos').parent().hide();
        $("#id_que_medicamentos").val('');
        $("#id_que_medicamentos").parent().removeClass('required');
        $("select[name='grupos_medicamentos']").parent().parent().hide();
        var currentVal = $("select[name='grupos_medicamentos']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearAlergiaMedicamentos();
        }
        $('#id_efeitos_adversos_medicamentos').parent().hide();
        $("#id_efeitos_adversos_medicamentos").val('');
        $("#id_efeitos_adversos_medicamentos").parent().removeClass('required');
    }
    if ($('#id_usa_medicamentos').val() == 'True') {
        $('#id_usa_que_medicamentos').parent().show();
        $("#id_usa_que_medicamentos").parent().addClass('required');
        $('#id_usa_medicamentos_ha_qt_tempo').parent().show();
        $("#id_usa_medicamentos_ha_qt_tempo").parent().addClass('required');
    } else {
        $('#id_usa_que_medicamentos').parent().hide();
        $("#id_usa_que_medicamentos").val('');
        $("#id_usa_que_medicamentos").parent().removeClass('required');
        $('#id_usa_medicamentos_ha_qt_tempo').parent().hide();
        $("#id_usa_medicamentos_ha_qt_tempo").val('');
        $("#id_usa_medicamentos_ha_qt_tempo").parent().removeClass('required');
    }
     if ($('#id_transtorno_psiquiatrico').val() == 'True') {
        $('#id_qual_transtorno_psiquiatrico').parent().show();
        $("#id_qual_transtorno_psiquiatrico").parent().addClass('required');
    } else {
        $('#id_qual_transtorno_psiquiatrico').parent().hide();
        $("#id_qual_transtorno_psiquiatrico").val('');
        $("#id_qual_transtorno_psiquiatrico").parent().removeClass('required');
    }
    if ($('#id_psiquiatra').val() == 'True') {
        $('#id_duracao_psiquiatria').parent().parent().show();
        $("#id_duracao_psiquiatria").parent().addClass('required');
        $("#id_tempo_psiquiatria").parent().addClass('required');
    } else {
        $('#id_duracao_psiquiatria').parent().parent().hide();
        $("#id_duracao_psiquiatria").val('');
        $("#id_duracao_psiquiatria").parent().removeClass('required');
        $("#id_tempo_psiquiatria").val('');
        $("#id_tempo_psiquiatria").parent().removeClass('required');
    }
    if ($('#id_lesoes_ortopedicas').val() == 'True') {
        $('#id_quais_lesoes_ortopedicas').parent().show();
        $("#id_quais_lesoes_ortopedicas").parent().addClass('required');
    } else {
        $('#id_quais_lesoes_ortopedicas').parent().hide();
        $("#id_quais_lesoes_ortopedicas").val('');
        $("#id_quais_lesoes_ortopedicas").parent().removeClass('required');
    }

    if ($('#id_doencas_previas').val() == 'True') {
        $('#id_que_doencas_previas').parent().show();
        $("#id_que_doencas_previas").parent().addClass('required');

        $('#id_idade_doenca_previa').parent().show();
        $("#id_idade_doenca_previa").parent().addClass('required');


    } else {
        $('#id_que_doencas_previas').parent().hide();
        $("#id_que_doencas_previas").val('');
        $("#id_que_doencas_previas").parent().removeClass('required');

        $('#id_idade_doenca_previa').parent().hide();
        $("#id_idade_doenca_previa").val('');
        $("#id_idade_doenca_previa").parent().removeClass('required');
    }

     if ($('#id_problema_auditivo').val() == 'True') {
        $('#id_qual_problema').parent().show();
        $("#id_qual_problema").parent().addClass('required');

        $('#id_usa_aparelho_auditivo').parent().show();
        $("#id_usa_aparelho_auditivo").parent().addClass('required');

    } else {
        $('#id_qual_problema').parent().hide();
        $("#id_qual_problema").val('');
        $("#id_qual_problema").parent().removeClass('required');

        $('#id_usa_aparelho_auditivo').parent().hide();
        $("#id_usa_aparelho_auditivo").val('');
        $("#id_usa_aparelho_auditivo").parent().removeClass('required');

        $('#id_usa_aparelho_em_qual_ouvido').parent().hide();
        $("#id_usa_aparelho_em_qual_ouvido").val('');
        $("#id_usa_aparelho_em_qual_ouvido").parent().removeClass('required');
    }
    if ($('#id_tem_deficiencia').val() == 'True') {
        $('#id_qual_deficiencia').parent().show();
        $("#id_qual_deficiencia").parent().addClass('required');
    } else {
        $('#id_qual_deficiencia').parent().hide();
        $("#id_qual_deficiencia").val('');
        $("#id_qual_deficiencia").parent().removeClass('required');
    }

     if ($('#id_tem_transtorno_neuro').val() == 'True') {
        $('#id_idade_diagnostico_transtorno').parent().show();
        $("#id_idade_diagnostico_transtorno").parent().addClass('required');
        $('#id_tem_acompanhamento_transtorno_neuro').parent().show();
        $("#id_tem_acompanhamento_transtorno_neuro").parent().addClass('required');
        $("select[name='quais_transtornos_neuro']").parent().show();
        $("select[name='quais_transtornos_neuro']").parent().addClass('required');
    } else {
        $('#id_idade_diagnostico_transtorno').parent().hide();
        $("#id_idade_diagnostico_transtorno").val('');
        $("#id_idade_diagnostico_transtorno").parent().removeClass('required');

        $('#id_tem_acompanhamento_transtorno_neuro').parent().hide();
        $("#id_tem_acompanhamento_transtorno_neuro").val('');
        $("#id_tem_acompanhamento_transtorno_neuro").parent().removeClass('required');

        $('#id_profissionais_acompanhamento_transtorno').parent().hide();
        $("#id_profissionais_acompanhamento_transtorno").val('');
        $("#id_profissionais_acompanhamento_transtorno").parent().removeClass('required');

        $("select[name='quais_transtornos_neuro']").parent().hide();
        var currentVal = $("select[name='quais_transtornos_neuro']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearTranstornos();
        }
    }

    if ($('#id_tem_acompanhamento_transtorno_neuro').val() == 'True') {
        $('#id_profissionais_acompanhamento_transtorno').parent().show();
        $("#id_profissionais_acompanhamento_transtorno").parent().addClass('required');
    } else {
        $('#id_profissionais_acompanhamento_transtorno').parent().hide();
        $("#id_profissionais_acompanhamento_transtorno").val('');
        $("#id_profissionais_acompanhamento_transtorno").parent().removeClass('required');
    }

    if ($("select[name='doencas_cronicas']").val() != '') {
        $("#id_tempo_doenca_cronica").parent().show();
        $("#id_tempo_doenca_cronica").parent().addClass('required');
    }
    else {
        $("#id_tempo_doenca_cronica").parent().hide();
        $("#id_tempo_doenca_cronica").val('');
        $("#id_tempo_doenca_cronica").parent().removeClass('required');
    };

    if ($('#id_usa_aparelho_auditivo').val() == 'True') {
        $('#id_usa_aparelho_em_qual_ouvido').parent().show();
        $("#id_usa_aparelho_em_qual_ouvido").parent().addClass('required');
    } else {
        $('#id_usa_aparelho_em_qual_ouvido').parent().hide();
        $("#id_usa_aparelho_em_qual_ouvido").val('');
        $("#id_usa_aparelho_em_qual_ouvido").parent().removeClass('required');
    }

    if ($('#id_tem_doenca_cronica').val() == 'True') {
        $("#id_tempo_doenca_cronica").parent().show();
        $("#id_tempo_doenca_cronica").parent().addClass('required');
        $("select[name='doencas_cronicas']").parent().parent().show();
        $("select[name='doencas_cronicas']").parent().addClass('required');



    } else {
        $('#id_tempo_doenca_cronica').parent().hide();
        $("#id_tempo_doenca_cronica").val('');
        $("#id_tempo_doenca_cronica").parent().removeClass('required');
        $("select[name='doencas_cronicas']").parent().parent().hide();
        $("select[name='doencas_cronicas']").parent().removeClass('required');
        var currentVal = $("select[name='doencas_cronicas']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearDoencasCronicas();
        }
    }



}
