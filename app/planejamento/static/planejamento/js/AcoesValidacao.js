$(document).ready(function(){
	// abre a janela de comentario para edicao ou visualizacao
	$('.ico_comentario').click(function(){
		// pega o elemento html que contem o comentario
		elHtml = $(this).next();
		
		if (elHtml.find('textarea').val() != '') {
			show_element_in_modal_window('Comentário sobre a validação', elHtml.attr('id'), true);
		} else {
			alert('Não existe comentário associado.');
		}
    });
});
