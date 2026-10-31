$(document).ready(function(){
	$("select[name=recursos]").change(function(){
		$('#recursos').children().css('display', 'none');
		$('#recursos').find('#tbl_' + $(this).val()).css('display', 'block');
		$('#recursos').find('#tbl_' + $(this).val()).css('width', '100%');
	});
	
	// garante que a página será carregada corretamente quando o usuário estiver utilizando o botão voltar
	$("select[name=recursos]").change();
})