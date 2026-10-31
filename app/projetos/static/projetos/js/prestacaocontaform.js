$(document).ready(function(){

	if ($('#id_tipo_relatorio').val() == 2 ){
		$("#id_mes_relatorio").parent().parent().hide();
		$("#id_ano_relatorio").parent().parent().hide();
	}



	else{
		$("#id_mes_relatorio").parent().parent().show();
		$("#id_ano_relatorio").parent().parent().show();
	}


});



