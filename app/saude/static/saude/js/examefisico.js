$(document).ready(function(){
    exibir_esconder_campo();
    $("#id_ectoscopia_alterada").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_acv_alterado").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_ar_alterado").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_abdome_alterado").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_mmi_alterados").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_mms_alterados").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_snl_alterado").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_esm_alterado").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_outras_alteracoes").on('change', function () {
        exibir_esconder_campo();
    });
})
function exibir_esconder_campo() {
    // ExameFisico
    if ($('#id_ectoscopia_alterada').val() == 'True') {
        $('#id_alteracao_ectoscopia').parent().show();
        $("#id_alteracao_ectoscopia").parent().addClass('required');
    } else {
        $('#id_alteracao_ectoscopia').parent().hide();
        $("#id_alteracao_ectoscopia").val('');
        $("#id_alteracao_ectoscopia").parent().removeClass('required');
    }
    if ($('#id_acv_alterado').val() == 'True') {
        $('#id_alteracao_acv').parent().show();
        $("#id_alteracao_acv").parent().addClass('required');
    } else {
        $('#id_alteracao_acv').parent().hide();
        $("#id_alteracao_acv").val('');
        $("#id_alteracao_acv").parent().removeClass('required');
    }
    if ($('#id_ar_alterado').val() == 'True') {
        $('#id_alteracao_ar').parent().show();
        $("#id_alteracao_ar").parent().addClass('required');
    } else {
        $('#id_alteracao_ar').parent().hide();
        $("#id_alteracao_ar").val('');
        $("#id_alteracao_ar").parent().removeClass('required');
    }
    if ($('#id_abdome_alterado').val() == 'True') {
        $('#id_alteracao_abdome').parent().show();
        $("#id_alteracao_abdome").parent().addClass('required');
    } else {
        $('#id_alteracao_abdome').parent().hide();
        $("#id_alteracao_abdome").val('');
        $("#id_alteracao_abdome").parent().removeClass('required');
    }
    if ($('#id_mmi_alterados').val() == 'True') {
        $('#id_alteracao_mmi').parent().show();
        $("#id_alteracao_mmi").parent().addClass('required');
    } else {
        $('#id_alteracao_mmi').parent().hide();
        $("#id_alteracao_mmi").val('');
        $("#id_alteracao_mmi").parent().removeClass('required');
    }
    if ($('#id_mms_alterados').val() == 'True') {
        $('#id_alteracao_mms').parent().show();
        $("#id_alteracao_mms").parent().addClass('required');
    } else {
        $('#id_alteracao_mms').parent().hide();
        $("#id_alteracao_mms").val('');
        $("#id_alteracao_mms").parent().removeClass('required');
    }

    if ($('#id_snl_alterado').val() == 'True') {
        $('#id_alteracao_snl').parent().show();
        $("#id_alteracao_snl").parent().addClass('required');
    } else {
        $('#id_alteracao_snl').parent().hide();
        $("#id_alteracao_snl").val('');
        $("#id_alteracao_snl").parent().removeClass('required');
    }


    if ($('#id_esm_alterado').val() == 'True') {
        $('#id_alteracao_esm').parent().show();
        $("#id_alteracao_esm").parent().addClass('required');
    } else {
        $('#id_alteracao_esm').parent().hide();
        $("#id_alteracao_esm").val('');
        $("#id_alteracao_esm").parent().removeClass('required');
    }


    if ($('#id_outras_alteracoes').val() == 'True') {
        $('#id_outras_alteracoes_descricao').parent().show();
        $("#id_outras_alteracoes_descricao").parent().addClass('required');
    } else {
        $('#id_outras_alteracoes_descricao').parent().hide();
        $("#id_outras_alteracoes_descricao").val('');
        $("#id_outras_alteracoes_descricao").parent().removeClass('required');
    }

}
