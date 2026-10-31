$(document).ready(function(){

	if ($('#id_vinculo').val() == 0 ){
		$("#id_campus").parent().parent().hide();
	}
	else{
		$("#id_campus").parent().parent().show();
	}

	$('#id_vinculo').on('change', function(){
    	if ($(this).val() == 0) {
	    	$("#id_campus").parent().parent().hide();
	 	}
	 	else{
	 	    $("#id_campus").parent().parent().show();
	 	}
	});
});



