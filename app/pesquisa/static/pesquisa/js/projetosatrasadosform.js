$(document).ready(function() {

	$("#id_ano").on('change', function(event){
		ano = $('#id_ano').val();
		$.ajax({
			method: "GET",
			url: "/pesquisa/filtrar_editais_completos_por_ano/",
			data: { "ano": ano },
			success: function(result, textStatus, jqXHR) {

				$('select[name=edital]').find('option').remove();
				$('select[name=edital]').append($('<option value="">-------</option>'));

				for (var i in result) {
					$('select[name=edital]').append($('<option value="'+result[i].pk+'">'+result[i].fields.titulo+'</option>'));
				}

			},
			error: function() {
			}
		});
		event.preventDefault();
	});
});
