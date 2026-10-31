$(document).ready(function(){
    recarrega();
	$('#id_programa').on('change', function(){
        recarrega();
	});
});

function recarrega(){

	var id_do_programa = $('#id_programa').val();

	$.ajax({
		method: "GET",
		url: "/ae/verifica_tipo_programa/",
		data: { "id_do_programa": id_do_programa },
		success: function(result, textStatus, jqXHR) {

			$("#id_setores_do_campus").parent().parent().show();

		},
		error: function() {

			$("#id_setores_do_campus").parent().parent().hide();

		}
	});
	}
