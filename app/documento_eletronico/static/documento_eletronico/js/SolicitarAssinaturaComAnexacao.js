$(document).ready(function()
{
	if($('input:radio[name=tipo_busca_setor]:checked').val()=="sem_despacho"){
		//$("select[name=destinatario_setor_autocompletar]").parent().parent().show();
	}
	else {
		//$("select[name=destinatario_setor_autocompletar]").parent().parent().hide();
		$("#id_despacho_corpo").parent().parent().hide();
		$("#id_papel").parent().parent().hide();
		$("#id_senha").parent().parent().hide();

	}
	if(($('input:radio[name=tipo_busca_setor]:checked').val()=="com_despacho") || $("#id_despacho_corpo").val() != ""){
		//$("select[name=destinatario_setor_autocompletar]").parent().parent().show();
		$("#id_despacho_corpo").parent().parent().show();
		$("#id_papel").parent().parent().show();
		$("#id_senha").parent().parent().show();
		}
	else{
		//$("select[name=destinatario_setor_autocompletar]").parent().parent().hide();
	}
	$("#id_tipo_busca_encaminhar_1").click(function(){
		//$("select[name=destinatario_setor_autocompletar]").parent().parent().show();
		$("#id_despacho_corpo").parent().parent().show();
		$("#id_papel").parent().parent().show();
		$("#id_senha").parent().parent().show();
	});
	$("#id_tipo_busca_encaminhar_0").click(function(){
		//$("select[name=destinatario_setor_autocompletar]").parent().parent().show();
		$("#id_despacho_corpo").parent().parent().hide();
		$("#id_papel").parent().parent().hide();
		$("#id_senha").parent().parent().hide();
	});
	$('.submit-row:first').hide();
});
