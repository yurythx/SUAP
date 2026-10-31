$(document).ready(function(){

    exibir_esconder_campo();

    $("#id_tem_questao_saude_mental").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_faz_acompanhamento_saude_mental").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_tentou_se_machucar").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_acompanhamento_saude_mental").on('change', function () {
        exibir_esconder_campo();
    });
});

function exibir_esconder_campo() {
    if ($('#id_tem_questao_saude_mental').val() == 'True') {
        $('#id_qual_questao_saude_mental').parent().show();
        $('#id_faz_acompanhamento_saude_mental').parent().show();
        $("#id_qual_questao_saude_mental").parent().addClass('required');
        $("#id_faz_acompanhamento_saude_mental").parent().addClass('required');
    } else {
        $('#id_qual_questao_saude_mental').parent().hide();
        $("#id_qual_questao_saude_mental").val('');
        $("#id_qual_questao_saude_mental").parent().removeClass('required');

        $('#id_faz_acompanhamento_saude_mental').parent().hide();
        $("#id_faz_acompanhamento_saude_mental").val('');
        $("#id_faz_acompanhamento_saude_mental").parent().removeClass('required');

        $('#id_acompanhamento_saude_mental').parent().hide();
        $("#id_acompanhamento_saude_mental").val('');
        $("#id_acompanhamento_saude_mental").parent().removeClass('required');
    }

    if ($('#id_faz_acompanhamento_saude_mental').val() == 'True') {
        $('#id_acompanhamento_saude_mental').parent().show();
        $("#id_acompanhamento_saude_mental").parent().addClass('required');
    } else {
        $('#id_acompanhamento_saude_mental').parent().hide();
        $("#id_acompanhamento_saude_mental").val('');
        $("#id_acompanhamento_saude_mental").parent().removeClass('required');
    }

    if ($('#id_tentou_se_machucar').val() == 'True') {
        $('#id_tentou_se_machucar_descricao').parent().show();
        $("#id_tentou_se_machucar_descricao").parent().addClass('required');
    } else {
        $('#id_tentou_se_machucar_descricao').parent().hide();
        $("#id_tentou_se_machucar_descricao").val('');
        $("#id_tentou_se_machucar_descricao").parent().removeClass('required');
    }
    if ($('#id_acompanhamento_saude_mental').val() == 'Outro') {
        $('#id_acompanhamento_saude_mental_outro').parent().show();
        $("#id_acompanhamento_saude_mental_outro").parent().addClass('required');
    } else {
        $('#id_acompanhamento_saude_mental_outro').parent().hide();
        $("#id_acompanhamento_saude_mental_outro").val('');
        $("#id_acompanhamento_saude_mental_outro").parent().removeClass('required');
    }
}
