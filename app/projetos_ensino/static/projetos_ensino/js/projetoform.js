$(document).ready(function(){

	if ($('#id_interdisciplinar').is(':checked')) {
            $('#id_disciplinas').parent().parent().show();
    } else {
        $('#id_disciplinas').parent().parent().hide();
	}

	if ($('#id_parceiros_externos').is(':checked')) {
            $('#id_quais_parceiros_externos').parent().parent().show();
    } else {
        $('#id_quais_parceiros_externos').parent().parent().hide();
	}

	exibir_esconder_campo();
    $("#id_interdisciplinar").on('change', function () {
        exibir_esconder_campo();
    });
    $("#id_parceiros_externos").on('change', function () {
        exibir_esconder_campo();
    });

    function exibir_esconder_campo() {

       if ($('#id_interdisciplinar').is(':checked')) {
            $('#id_disciplinas').parent().parent().show();
       } else {
            $('#id_disciplinas').val("");
            $('#id_disciplinas').parent().parent().hide();
       }

       if ($('#id_parceiros_externos').is(':checked')) {
            $('#id_quais_parceiros_externos').parent().parent().show();
       } else {
            $('#id_quais_parceiros_externos').val("");
            $('#id_quais_parceiros_externos').parent().parent().hide();
       }

    }
});
