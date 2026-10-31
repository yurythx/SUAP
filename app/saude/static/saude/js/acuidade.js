$(document).ready(function () {
    exibir_esconder_campo();
    $("#id_usa_lente").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_teste_com_lente").on('change', function () {
        exibir_esconder_campo();
    });
});


function exibir_esconder_campo() {
     if ($('#id_usa_lente').val() == 'True') {
        $('#id_usa_lente_detalhes').parent().show();
        $("#id_usa_lente_detalhes").parent().addClass('required');
    } else {
        $('#id_usa_lente_detalhes').parent().hide();
        $("#id_usa_lente_detalhes").val('');
        $("#id_usa_lente_detalhes").parent().removeClass('required');
    }

    if ($('#id_teste_com_lente').val() == 'False') {
        $('#id_usa_lente').parent().show();
        $("#id_usa_lente").parent().addClass('required');

    } else {
        $('#id_usa_lente').parent().hide();
        $("#id_usa_lente").val('');
        $("#id_usa_lente").parent().removeClass('required');
        $('#id_usa_lente_detalhes').parent().hide();
        $("#id_usa_lente_detalhes").val('');
        $("#id_usa_lente_detalhes").parent().removeClass('required');
    }
}
