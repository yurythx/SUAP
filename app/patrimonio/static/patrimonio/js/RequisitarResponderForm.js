$(document).ready(function(){
	
	if($("input[name=resposta]:checked").val() == undefined){
		$("#id_resposta_0").attr('checked', true);
	}	
	
	if($("input[name=resposta]:checked").val() == "aceitar"){
		$("textarea[name=texto_resposta]").parent().hide();
	}
	else if($("input[name=resposta]::checked").val() == "negar"){
		$("textarea[name=texto_resposta]").parent().show();
	}
		
	$("#id_resposta_0").change(function(){
		$("textarea[name=texto_resposta]").parent().hide();
	});
	
	$("#id_resposta_1").change(function(){
		$("textarea[name=texto_resposta]").parent().show();
	});
		
})