$(document).ready(function() {
	// remove o label padrão do django
   	$('input.labeless').prev().remove();
	$('input.labeless').next().addClass('help_marginless');
	$('input.labeless').next().removeClass('help');
	
	// adicionar uma cor padrão que indica que os campos estão desabilitados
	$('input[readonly=true]').css('background-color', '#eee');
	$('textarea[readonly=true]').css('background-color', '#eee');
		
	// reseta o formulário da página
	$('#btn_reset_forms').click(function () {
		$('form').each(function() {
			this.reset();
		});
	});
	
	// oculta e expande as caixas com a classe cx_expansivel
	$('legend.cx_expansivel_legenda').click(function () {
		$(this).parent().find('.cx_expansivel_conteudo').toggle();
		
	});
	
	// controla o progressbar
	$(".progressbar").each(function() {
		$(this).progressBar($(this).text(), {showText: false});
	});
});

// redireciona form
function submeter_form(campo) {
    $('#'+campo.id).parents('form').submit();
}

// indica a altura da area util da janela
function window_height() {
	return parseInt($(window).height());
}

// indica a largura da area util da janela
function window_width() {
	return parseInt($(window).width());
}

/* 
 * apresenta elemento oculto em formato de janela
 * params: 	title 		= mensagem que aparece como titulo da janela
 * 			element_id 	= elemento que sera apresentado na janela
 * 			close_btn 	= indica se a janela deve ter um botao para fechar 
 */
function show_element_in_modal_window(title, element_id, close_btn) {
	// altura e largura do browser
	hWindow = window_height();
	bWindow = window_width();
			
	elHtml = '#' + element_id
	elHtmlClone = $(elHtml).clone(true).css('display', 'block');
	
	// adiciona os elementos de bloqueio e caixa modal
	$('main').append('<div id="winmod_block"></div>');
	$('main').append('<div id="winmod"></div>');
	
	// define a barra de titulo da janela
	title_bar = '';
	if (close_btn) {
		title_bar += '<h3 id="winmod_title">' + title + '<img src="/static/comum/img/close_modal_box.png" onclick="close_modal_window()" /></h3>';
	} else {
		title_bar += '<h3 id="winmod_title">' + title + '</h3>';
	}
	
	$('#winmod').append(title_bar);
	$('#winmod').append('<div id="winmod_content"></div>');
	
	elHtmlClone.appendTo('#winmod #winmod_content');
	
	// atualiza o posicionamento da janela modal
	if (parseInt((hWindow / 3) - ($('#winmod').height() / 3)) > 10) {
		$('#winmod').css('top', parseInt((hWindow / 3) - ($('#winmod').height() / 3)) + 'px');
	} else {
		$('#winmod').css('top', parseInt((hWindow / 2) - ($('#winmod').height() / 2)) + 'px');
	}
	$('#winmod').css('left', parseInt((bWindow / 2) - ($('#winmod').width() / 2)) + 'px');
	
}

// fecha o elemento de bloqueio para janelas modais
function close_modal_window() {
	$('#winmod').remove();
	$('#winmod_block').remove();
}
