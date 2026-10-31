$(document).ready(function() {

	$("#id_ano").on('change', function(event){
		setor_id = $('#setor_id').val();
		$.ajax({
			method: "GET",
			url: "/avaliacao_integrada/obter_membros_por_setor/" + setor_id,
			// data: { "setor_id": ano },
			success: function(result, textStatus, jqXHR) {

				$('select[name=vinculos_membros]').find('option').remove();
				$('select[name=vinculos_membros]').append($('<option value="">-------</option>'));

				for (var i in result) {
					$('select[name=vinculos_membros]').append($('<option value="'+result[i].pk+'">'+result[i].fields.titulo+'</option>'));
				}

			},
			error: function() {
			}
		});
		event.preventDefault();
	});
});
