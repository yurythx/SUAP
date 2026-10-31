$(document).ready(function() {
    exibir_esconder_campo();
	$("select[name='turma']").on('change', function () {
	    setTimeout(exibir_esconder_campo, 1000);

    });
    $("select[name='diario']").on('change', function () {
        setTimeout(exibir_esconder_campo, 1000);
    });
    $("#id_lista_alunos").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {
    if (($('.field-diario ul li').length > 1 ) || ($('.field-turma ul li').length > 1) || !($('#id_lista_alunos').val() == "" ))  {

		$('#id_texto_aceite').parent().parent().show();
        $('#id_aceite').parent().parent().show();
	}



	else{
		$('#id_texto_aceite').parent().parent().hide();
        $('#id_aceite').parent().parent().hide();
	}
}
