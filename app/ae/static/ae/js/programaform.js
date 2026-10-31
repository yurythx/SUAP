$(document).ready(function(){
    exibir_esconder_campo();
    $("select[name='tipo_programa']").on('change', function () {
        exibir_esconder_campo();
    });
});

function exibir_esconder_campo() {
    if ($("select[name='tipo_programa']").val() == '1'){
        $("#id_qtd_faltas_bloqueio_alimentacao").parent().show();
        $("#id_qtd_faltas_bloqueio_alimentacao").parent().addClass('required');
    } else {
        $('#id_qtd_faltas_bloqueio_alimentacao').parent().hide();
        $("#id_qtd_faltas_bloqueio_alimentacao").val('');
        $("#id_qtd_faltas_bloqueio_alimentacao").parent().removeClass('required');
    }
}
