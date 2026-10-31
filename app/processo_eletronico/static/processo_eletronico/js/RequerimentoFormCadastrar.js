$(document).ready(function(){
	if($('input:radio[name=tipo_busca_setor]:checked').val()=="arvore"){
		$("#tree-destinatario_setor_arvore").parent().parent().show();
	}
	else {
		$("#tree-destinatario_setor_arvore").parent().parent().hide();
	}

	if($('input:radio[name=tipo_busca_setor]:checked').val()=="autocompletar"){
		$("select[name=destinatario_setor_autocompletar]").parent().parent().show();
	}
	else{
		$("select[name=destinatario_setor_autocompletar]").parent().parent().hide();
	}

	if($('input:radio[name=tipo_busca_setor]:checked').val()=="meu_setor"){
		$("input[name=destinatario_setor_arvore]").parent().parent().hide();
		$("select[name=destinatario_setor_autocompletar]").parent().parent().hide();
	}

	$("#id_tipo_busca_setor_1").click(function(){
		$("select[name=destinatario_setor_autocompletar]").parent().parent().hide();
		$("#tree-destinatario_setor_arvore").parent().parent().show();
	});

	$("#id_tipo_busca_setor_0").click(function(){
		$("select[name=destinatario_setor_autocompletar]").parent().parent().show();
		$("#tree-destinatario_setor_arvore").parent().parent().hide();
	});

	$("#id_tipo_busca_setor_2").click(function(){
		$("select[name=destinatario_setor_autocompletar]").parent().parent().hide();
		$("#tree-destinatario_setor_arvore").parent().parent().hide();
	});

});