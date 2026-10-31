$(document).ready(function(){

	if ($('#id_status_avaliacao').val() == 4 ){
		$("#id_pontos").parent().parent().show();

	}
	else {
		$("#id_pontos").parent().parent().hide();
	}

	$('#id_status_avaliacao').on('change', function(){
		if ($(this).val() == 4) {
			$("#id_pontos").parent().parent().show();
		}
		else {
			$("#id_pontos").parent().parent().hide();
	 	}
	});

});
