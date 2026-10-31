$(document).ready(function(){
	// atribui espaçamento de acordo com a largura das colunas fixas
	largura_colunas_fixas = $(".tbl_colunas_fixas").width();
	$(".cx_conteudo").css('left', largura_colunas_fixas + 1);
	
	// ajusta a largura da caixa de conteudo
	$(".cx_conteudo").width($(".cx_conteudo").width() - largura_colunas_fixas);
	
	// ajusta a largura da caixa que contem as tabelas para que seja possivel visualizar a barra de rolagem horizontal
	altura_cx_conteudo = $(".cx_conteudo").height();
	$(".cx_tabela_plus").height(altura_cx_conteudo + 2);
})