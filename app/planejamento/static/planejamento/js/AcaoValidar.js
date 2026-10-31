//onclick="abrir_janela('Lista de atividades', 'atividades_{{ acao.id }}')"
function loadAcao(){
	// oculta o botao para salvar a validacao
	$('#btn_salvar').hide();
	
	// abre caixa de comentario para as validacoes que precisam desta informacao
    $('.comentario_obg').change(function(){
		id_acao = $(this).attr('name');
       	show_element_in_modal_window('Comentário sobre a validação', 'cx_comentario_' + id_acao, false);
    });
	
	// remove o comentario associado
    $('.comentario_n_obg').change(function(){
		id_acao = $(this).attr('name');
		// remove o comentario associado
		$('#cx_comentario_'+id_acao).find('textarea').text('');
       	$('#cx_comentario_'+id_acao).prev('img.ico_comentario').attr('src', '/static/comum/img/comments_smb.png');
		$('#btn_salvar').show();
    });
	
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
}

function inserir_comentario(id_elemento) {
	elHtml = '.' + id_elemento;
	
	// pega o atual comentário adicionado e atribui ao elemento
	coment = $('#winmod').find(elHtml).val().replace(/^\s+|\s+$/g,"");
	$(elHtml).text(coment);
	
	// verifica se existe comentario associado e atualiza o icone
	if (coment == '') {
		alert('Forneça um comentário para justificar esta validação.');
		return;
	}
	
	$(elHtml).parent().parent().find('.ico_comentario').attr('src', '/static/comum/img/comments.png');
	
	// apresenta o botao para salvar as informacoes
	$('#btn_salvar').show();
	
	// fecha a janela modal
	close_modal_window();
}
