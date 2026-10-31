$(document).ready(function(){



	$('#id_inscricao_situacao').on('change', function(){
		if ($(this).val() != 1) {

			$("#id_programa").parent().parent().hide();
		}
		else {
			$("#id_programa").parent().parent().show();
	 	}
	});

	$('#id_participacao_situacao').on('change', function(){
		if ($(this).val() != 1 && $(this).val() != 4) {

			$("#id_participantes").parent().parent().hide();
		}
		else {
			$("#id_participantes").parent().parent().show();
	 	}
	});



});
