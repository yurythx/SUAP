$(document).ready(function () {
    exibir_esconder_campo();
    $("#id_tipo_relatorio").on('change', function () {
        exibir_esconder_campo();
    });
});

function exibir_esconder_campo() {
    // Antropometria
    if ($('#id_tipo_relatorio').val() == '7') {
        $('#id_vinculo').parent().parent().show();
    } else {
        $('#id_vinculo').parent().parent().hide();
    }

}
