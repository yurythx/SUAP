$(document).ready(function() {
	$("#id_ano").on('change', function(event){
		ano = $('#id_ano').val();
		$.ajax({
			method: "GET",
			url: "/projetos/filtrar_editais_por_ano/",
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
	$("#id_edital").on('change', function(event){
		edital = $('#id_edital').val();
		$.ajax({
			method: "GET",
			url: "/projetos/filtrar_recursos_por_edital/",
			data: { "edital": edital },
			success: function(result, textStatus, jqXHR) {

				$('select[name=recurso]').find('option').remove();
				$('select[name=recurso]').append($('<option value="">-------</option>'));
                console.log(result);
				for (var i in result) {
					$('select[name=recurso]').append($('<option value="'+result[i].id+'">'+result[i].titulo+'</option>'));
				}
			},
			error: function() {
			}
		});
		event.preventDefault();
	});



});
