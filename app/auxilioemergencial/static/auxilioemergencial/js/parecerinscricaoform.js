$(document).ready(function(){
    console.log($('#id_parecer').val());
    if ($('#id_parecer').val() == 'Deferido'){
        $("#id_valor").parent().parent().show();
        $("#id_documentacao_pendente").parent().parent().hide();
        $("#id_data_limite").parent().parent().hide();
    }
    else if ($('#id_parecer').val() == 'Pendente de documentação complementar'){
        $("#id_documentacao_pendente").parent().parent().show();
        $("#id_data_limite").parent().parent().show();
        $("#id_valor").parent().parent().hide();
    }
    else {
        $("#id_valor").parent().parent().hide();
        $("#id_documentacao_pendente").parent().parent().hide();
        $("#id_data_limite").parent().parent().hide();
    }

	$('#id_parecer').on('change', function(){
		if ($(this).val() == 'Deferido') {
			$("#id_valor").parent().parent().show();
		}
		else {
            $("#id_valor").parent().parent().hide();
	 	}

	 	if ($(this).val() == 'Pendente de documentação complementar') {
			$("#id_documentacao_pendente").parent().parent().show();
            $("#id_data_limite").parent().parent().show();
		}
		else {
            $("#id_documentacao_pendente").parent().parent().hide();
            $("#id_data_limite").parent().parent().hide();
	 	}
	});

})
