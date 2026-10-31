$(document).ready(function(){
    change_recorrencia();
	$("#id_recorrencia").on('change', function(){
        change_recorrencia();
	});
});

function change_recorrencia(){
    if(!$('#id_recorrencia').val() || $('#id_recorrencia').val() === "evento_unico"){
        $('#id_recorrencia').parents('fieldset').first().next().hide();
    } else {
        $('#id_recorrencia').parents('fieldset').first().next().show();
    }
}
