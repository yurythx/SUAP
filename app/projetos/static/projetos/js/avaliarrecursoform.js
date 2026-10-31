$(document).ready(function(){
	$('#id_recurso_aceito').on('change', function(){
    	if ($('#id_recurso_aceito').is(':checked')) {
	 		$("#id_nova_pontuacao").prop('disabled', false);
	 	}
        else {
	 		$("#id_nova_pontuacao").prop('disabled', 'disabled');
        }
	});
	if ($('#id_recurso_aceito').is(':checked')) {
        $("#id_nova_pontuacao").prop('disabled', false);
    }
    else {
        $("#id_nova_pontuacao").prop('disabled', 'disabled');
    }
});
