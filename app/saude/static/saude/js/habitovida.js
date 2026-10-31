$(document).ready(function(){

    exibir_esconder_campo();

    $("#id_atividade_fisica").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_fuma").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_bebe").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_usa_drogas").on('change', function () {
        exibir_esconder_campo();
    });


    $("#id_vida_sexual_ativa").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_metodo_contraceptivo").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_uso_internet").on('change', function () {
        exibir_esconder_campo();
    });
});

function clearDrogas() {
    $("select[name='que_drogas']").val(null).trigger('change');
}
function clearMetodosContraceptivos() {
    $("select[name='qual_metodo_contraceptivo']").val(null).trigger('change');
}


function exibir_esconder_campo() {
    if ($('#id_atividade_fisica').val() == 'True') {
        $('#id_qual_atividade').parent().show();
        $('#id_frequencia_semanal').parent().parent().show();
        $("#id_qual_atividade").parent().addClass('required');
        $("#id_frequencia_semanal").parent().addClass('required');
        $("#id_duracao_atividade").parent().addClass('required');
    } else {
        $('#id_qual_atividade').parent().hide();
        $('#id_frequencia_semanal').parent().parent().hide();
        $("#id_qual_atividade").val('');
        $("#id_qual_atividade").parent().removeClass('required');
        $("#id_frequencia_semanal").val(1);
        $("#id_duracao_atividade").val(1);
        $("#id_frequencia_semanal").parent().removeClass('required');
        $("#id_duracao_atividade").parent().removeClass('required');
    }

    if ($('#id_fuma').val() == 'True') {
        $('#id_frequencia_uso_fumo').parent().show();
        $("#id_frequencia_uso_fumo").parent().addClass('required');
        $('#id_idade_fumo').parent().show();
        $("#id_idade_fumo").parent().addClass('required');
    } else {
        $('#id_frequencia_uso_fumo').parent().hide();
        $("#id_frequencia_uso_fumo").val('');
        $("#id_frequencia_uso_fumo").parent().removeClass('required');
        $('#id_idade_fumo').parent().hide();
        $("#id_idade_fumo").val('');
        $("#id_idade_fumo").parent().removeClass('required');
    }

    if ($('#id_bebe').val() == 'True') {
        $('#id_frequencia_uso_bebida').parent().show();
        $("#id_frequencia_uso_bebida").parent().addClass('required');
        $('#id_idade_bebida').parent().show();
        $("#id_idade_bebida").parent().addClass('required');
    } else {
        $('#id_frequencia_uso_bebida').parent().hide();
        $("#id_frequencia_uso_bebida").val('');
        $("#id_frequencia_uso_bebida").parent().removeClass('required');
        $('#id_idade_bebida').parent().hide();
        $("#id_idade_bebida").val('');
        $("#id_idade_bebida").parent().removeClass('required');
    }

    if ($('#id_usa_drogas').val() == 'True') {
        $("select[name='que_drogas']").parent().show();
        $("select[name='que_drogas']").parent().addClass('required');
        $('#id_idade_drogas').parent().show();
        $("#id_idade_drogas").parent().addClass('required');
        $('#id_frequencia_uso_droga').parent().show();
        $("#id_frequencia_uso_droga").parent().addClass('required');
    } else {
        $("select[name='que_drogas']").parent().hide();
        var currentVal = $("select[name='que_drogas']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearDrogas();
        }
        $("#id_que_drogas").parent().removeClass('required');
        $('#id_idade_drogas').parent().hide();
        $("#id_idade_drogas").val('');
        $("#id_idade_drogas").parent().removeClass('required');
        $('#id_frequencia_uso_droga').parent().hide();
        $("#id_frequencia_uso_droga").val('');
        $("#id_frequencia_uso_droga").parent().removeClass('required');
    }




    if ($('#id_vida_sexual_ativa').val() == 'True') {
        $('#id_metodo_contraceptivo').parent().show();
        $("#id_metodo_contraceptivo").parent().addClass('required');
    } else {
        $("select[name='qual_metodo_contraceptivo']").parent().hide();
        $('#id_metodo_contraceptivo').parent().hide();
        $("#id_metodo_contraceptivo").val('');
        $("#id_metodo_contraceptivo").parent().removeClass('required');
        $('#id_qual_metodo_contraceptivo').parent().hide();
        var currentVal = $("select[name='qual_metodo_contraceptivo']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearMetodosContraceptivos();
        }
    }
    if ($('#id_metodo_contraceptivo').val() == 'True') {
        $("select[name='qual_metodo_contraceptivo']").parent().show();
        $("select[name='qual_metodo_contraceptivo']").parent().addClass('required');
    } else {
        $("select[name='qual_metodo_contraceptivo']").parent().hide();
        $("select[name='qual_metodo_contraceptivo']").parent().removeClass('required');
        var currentVal = $("select[name='qual_metodo_contraceptivo']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearMetodosContraceptivos();
        }
    }
    if ($('#id_uso_internet').val() == 'True') {
        $('#id_tempo_uso_internet').parent().show();
        $("#id_tempo_uso_internet").parent().addClass('required');
        $('#id_objetivo_uso_internet_0').parent().parent().parent().parent().show();
        $("#id_objetivo_uso_internet_0").parent().parent().parent().parent().addClass('required');
    } else {
        $('#id_tempo_uso_internet').parent().hide();

        $("#id_tempo_uso_internet").parent().removeClass('required');
        $('#id_objetivo_uso_internet_0').parent().parent().parent().parent().hide();

        $("#id_objetivo_uso_internet_0").parent().parent().parent().parent().removeClass('required');

    }
}
