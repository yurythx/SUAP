$(document).ready(function(){
	if($('input:radio[name=tipo_protocolo]:checked').val()=="eletronico"){
		$("input[name=protocolo_eletronico]").parent().parent().show();
	}
	else {
		$("input[name=protocolo_eletronico]").parent().parent().hide();
	}

	if($('input:radio[name=tipo_protocolo]:checked').val()=="fisico"){
		$("input[name=protocolo_fisico]").parent().parent().show();
	}
	else{
		$("input[name=protocolo_fisico]").parent().parent().hide();
	}

	$("#id_tipo_protocolo_0").click(function(){
		$("input[name=protocolo_fisico]").parent().parent().hide();
		$("input[name=protocolo_eletronico]").parent().parent().show();
	});
	$("#id_tipo_protocolo_1").click(function(){
		$("input[name=protocolo_fisico]").parent().parent().show();
		$("input[name=protocolo_eletronico]").parent().parent().hide();
	});
});