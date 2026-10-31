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

	$('#id_clonar_comissao_edital').parent().parent().hide();
	$("#id_clonar_comissao").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {
    if ($('#id_clonar_comissao').is(':checked')) {
        $('#id_membros').parent().parent().hide();
        $('#id_clonar_comissao_edital').parent().parent().show();
    } else {
        $('#id_clonar_comissao_edital').parent().parent().hide();
        $('#id_membros').parent().parent().show();
    }
}

