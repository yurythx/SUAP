$(document).ready(function () {
    exibir_esconder_campo();
    $("#id_formato").on('change', function () {
        exibir_esconder_campo();
    });
});

function exibir_esconder_campo() {
    if ($("#id_formato").val() === 'anual') {
        $("#id_mes").val(0);
        $('#id_mes').closest('.form-row').hide();
    } else {
        $('#id_mes').closest('.form-row').show();
    }
}
