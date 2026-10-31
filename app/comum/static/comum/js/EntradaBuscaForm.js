$(document).ready(function(){
	
	if ($("select[name=tipo_material]").val() == ""){
		$("input[name=descricao_material]").parent().parent().hide();
	} else{
		$("input[name=descricao_material]").parent().parent().show();
	}
	
	if($("select[name=tipo_entrada]").val() == "1"){
		$("input[name=numero_nota_fiscal]").parent().parent().show();
		$("input[name=empenho]").parent().parent().show();		
	}
	else {
		$("input[name=numero_nota_fiscal]").parent().parent().hide();
		$("input[name=empenho]").parent().parent().hide();		
	}	
	
	$("#id_tipo_entrada").change(function(){
		if($("select[name=tipo_entrada]").val() == "1"){
			$("input[name=numero_nota_fiscal]").parent().parent().show();
			$("input[name=empenho]").parent().parent().show();	
		}else {
			$("input[name=numero_nota_fiscal]").parent().parent().hide();
			$("input[name=empenho]").parent().parent().hide();	
		}		
	});
	
	$("#id_tipo_material").change(function(){
		if($("select[name=tipo_material]").val()==""){
			$("input[name=descricao_material]").parent().parent().hide();
		} else {
			$("input[name=descricao_material]").parent().parent().show();
		}
	});
	
});