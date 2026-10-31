$(document).ready(function(){
	$("select[name=tipo_nota]").change(function(){
		$('#tipo_notas').children().css('display', 'none');
		$('#tipo_notas').find('#tbl_' + $(this).val()).css('display', 'block');
		$('#tipo_notas').find('#tbl_' + $(this).val()).css('width', '100%');
	});
	
	// garante que a página será carregada corretamente quando o usuário estiver utilizando o botão voltar
	$("select[name=tipo_nota]").change();
})