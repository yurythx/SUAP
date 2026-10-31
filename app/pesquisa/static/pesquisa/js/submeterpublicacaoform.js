$(document).ready(function () {
    exibir_esconder_campo();

    $("#id_periodicidade_evento").on('change', function () {
        exibir_esconder_campo();
    });
    $("#id_tem_issn").on('change', function () {
        exibir_esconder_campo();
    });
    $("#id_tem_isbn").on('change', function () {
        exibir_esconder_campo();
    });
});

function exibir_esconder_campo() {
    if ($('#id_periodicidade_evento').val() == 'Outro/Especifique') {
        $('#id_periodicidade_outro_evento').parent().parent().show();
        $("#id_periodicidade_outro_evento").parent().parent().addClass("required");
        $("#id_periodicidade_outro_evento").parent().prop("required", true);
    }
    else {
        $('#id_periodicidade_outro_evento').parent().parent().hide();
        $("#id_periodicidade_outro_evento").parent().parent().parent().removeClass("required");
        $("#id_periodicidade_outro_evento").parent().parent().parent().prop("required", false);
    }

    if ($('#id_tem_issn').val() == 'True') {
        $('#id_issn_evento').parent().parent().show();
        $("#id_issn_evento").parent().parent().addClass("required");
        $("#id_issn_evento").parent().prop("required", true);
    }
    else {
        $('#id_issn_evento').parent().parent().hide();
        $("#id_issn_evento").parent().parent().parent().removeClass("required");
        $("#id_issn_evento").parent().parent().parent().prop("required", false);
    }

    if ($('#id_tem_isbn').val() == 'True') {
        $('#id_isbn_evento').parent().parent().show();
        $("#id_isbn_evento").parent().parent().addClass("required");
        $("#id_isbn_evento").parent().prop("required", true);
    }
    else {
        $('#id_isbn_evento').parent().parent().hide();
        $("#id_isbn_evento").parent().parent().parent().removeClass("required");
        $("#id_isbn_evento").parent().parent().parent().prop("required", false);
    }

}
