$(document).ready(function () {
    exibir_esconder_campo();

    $("#id_tipo_submissao").on('change', function () {
        exibir_esconder_campo();
    });
});

function exibir_esconder_campo() {
    if ($('#id_tipo_submissao').val() == 'Impresso') {
        $('#id_recurso_impressao').parent().parent().show();
    }
    else {
        $('#id_recurso_impressao').parent().parent().hide();
    }

}
