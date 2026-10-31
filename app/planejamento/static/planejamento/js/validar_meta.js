$(document).ready(function(){
	bind_form_submit();
})

function bind_form_submit(){
	$('#changelist-search select').each(function() {
		$(this).change(function () {
			$('#changelist-search').submit();
		});
	});
}

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
	// close_modal_window();
}

function loadAcaoValidacao(tr_id, meta_id) {
		$('#tabela_metas tr:#' + tr_id.id).after('<tr id="tr_validacao"><td id="td_validacao" colspan="7">Nova linha</td></tr>');
		$('#td_validacao').load('/planejamento/acao/validar/' + meta_id + '/', loadAcao);
}

var valiar_acao = function(meta_id) {
	tr_id =  $('#tabela_metas tr:#tr_meta_' + meta_id).get(0);
	url_reload = document.URL + ' #tabela_metas';
	
	if (tr_id.nextElementSibling && tr_id.nextElementSibling.id == 'tr_validacao') {
		$('#tabela_metas').load(url_reload);
	} else {
		if ($('#tabela_metas tr:#tr_validacao').length > 0) {
			$("#tr_validacao").remove();
			$('#tabela_metas').load(url_reload, function () {
				loadAcaoValidacao(tr_id, meta_id);
			});
		}
		loadAcaoValidacao(tr_id, meta_id);
	}
}
