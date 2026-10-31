$(document).ready(function(){
    exibir_esconder_campo();
    $("#id_perda_peso").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_ganho_peso").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_tem_alergia_alimentos").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='alergia_alimentos']").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_tem_intolerancia_alimentar").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='intolerancia_alimentar']").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_possui_necessidade_alimentar").on('change', function () {
        exibir_esconder_campo();
    });

})
function clearAlergiaAlimentos() {
    $("select[name='alergia_alimentos']").val(null).trigger('change');
}
function clearIntolerancia() {
    $("select[name='intolerancia_alimentar']").val(null).trigger('change');
}
function exibir_esconder_campo() {

    if ($("#id_perda_peso").val() == 'True') {
        $("#id_quanto_perdeu").parent().show();
        $("#id_tempo_perda").parent().show();
        $("#id_quanto_perdeu").parent().addClass('required');
        $("#id_tempo_perda").parent().addClass('required');
    }
    else {
        $("#id_quanto_perdeu").parent().hide();
        $("#id_tempo_perda").parent().hide();
        $("#id_quanto_perdeu").val('');
        $("#id_tempo_perda").val('');
        $("#id_quanto_perdeu").parent().removeClass('required');
        $("#id_tempo_perda").parent().removeClass('required');
    };

    if ($("#id_ganho_peso").val() == 'True') {
        $("#id_quanto_ganhou").parent().show();
        $("#id_tempo_ganho").parent().show();
        $("#id_quanto_ganhou").parent().addClass('required');
        $("#id_tempo_ganho").parent().addClass('required');
    }
    else {
        $("#id_quanto_ganhou").parent().hide();
        $("#id_tempo_ganho").parent().hide();
        $("#id_quanto_ganhou").val('');
        $("#id_tempo_ganho").val('');
        $("#id_quanto_ganhou").parent().removeClass('required');
        $("#id_tempo_ganho").parent().removeClass('required');
    };

    if ($("#id_tem_alergia_alimentos").val() == 'True') {
        $("#id_diagnostico_alergia_alimentos").parent().show();
        $("select[name='alergia_alimentos']").parent().parent().show();
        $("#id_diagnostico_alergia_alimentos").parent().addClass('required');
        $("select[name='alergia_alimentos']").parent().addClass('required');
    }
    else {
        $("#id_diagnostico_alergia_alimentos").parent().hide();
        $("select[name='alergia_alimentos']").parent().parent().hide();
        $("#id_alergia_alimentos_outros").parent().hide();

        $("#id_diagnostico_alergia_alimentos").val('');
        var currentVal = $("select[name='alergia_alimentos']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearAlergiaAlimentos();
        }
        $("#id_alergia_alimentos_outros").val('');

        $("#id_diagnostico_alergia_alimentos").parent().removeClass('required');
        $("#id_alergia_alimentos_outros").parent().removeClass('required');
    };

    if ($("select[name='alergia_alimentos']").val() && $("select[name='alergia_alimentos']").val().includes('13')) {

        $("#id_alergia_alimentos_outros").parent().show();
        $("#id_alergia_alimentos_outros").parent().addClass('required');
    }
    else {
        $("#id_alergia_alimentos_outros").parent().hide();
        $("#id_alergia_alimentos_outros").val('');
        $("#id_alergia_alimentos_outros").parent().removeClass('required');
    };

    if ($("#id_tem_intolerancia_alimentar").val() == 'True') {
        $("#id_diagnostico_intolerancia_alimentar").parent().show();
        $("select[name='intolerancia_alimentar']").parent().parent().show();
        $("#id_diagnostico_intolerancia_alimentar").parent().addClass('required');
        $("select[name='intolerancia_alimentar']").parent().addClass('required');
    }
    else {
        $("#id_diagnostico_intolerancia_alimentar").parent().hide();
        $("select[name='intolerancia_alimentar']").parent().parent().hide();
        $("#id_intolerancia_alimentar_outros").parent().hide();

        $("#id_diagnostico_intolerancia_alimentar").val('');
        var currentVal = $("select[name='intolerancia_alimentar']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearIntolerancia();
        }
        $("#id_intolerancia_alimentar_outros").val('');

        $("#id_diagnostico_intolerancia_alimentar").parent().removeClass('required');
        $("#id_intolerancia_alimentar_outros").parent().removeClass('required');
    };

    if ($("select[name='intolerancia_alimentar']").val() && $("select[name='intolerancia_alimentar']").val().includes('3')) {

        $("#id_intolerancia_alimentar_outros").parent().show();
        $("#id_intolerancia_alimentar_outros").parent().addClass('required');
    }
    else {
        $("#id_intolerancia_alimentar_outros").parent().hide();
        $("#id_intolerancia_alimentar_outros").val('');
        $("#id_intolerancia_alimentar_outros").parent().removeClass('required');
    };

    if ($("#id_possui_necessidade_alimentar").val() == 'True') {
        $("#id_qual_necessidade_alimentar").parent().show();
        $("#id_qual_necessidade_alimentar").parent().addClass('required');
    }
    else {
        $("#id_qual_necessidade_alimentar").parent().hide();
        $("#id_qual_necessidade_alimentar").val('');
        $("#id_qual_necessidade_alimentar").parent().removeClass('required');
    };
}
