$(document).ready(function(){

	 exibir_esconder_campo();

    $("#id_tipo_destinatario").on('change', function () {
        exibir_esconder_campo();
    });

})

function clearEditais() {
    $("select[name='editais']").val(null).trigger('change');
}

function exibir_esconder_campo() {
    if ($("#id_tipo_destinatario").val() == 'Aval') {
        $("select[name='editais']").parent().parent().show();
        $("select[name='editais']").parent().addClass('required');
    }
    else {
        $("select[name='editais']").parent().parent().hide();

        $("#id_editais").parent().removeClass('required');
        var currentVal = $("select[name='editais']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearEditais();
        }
    }
};
