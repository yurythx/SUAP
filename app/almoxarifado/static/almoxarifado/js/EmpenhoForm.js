$(document).ready(function(){
	if($("input[name=tipo_pessoa]:checked").val() == undefined){
		$("#id_tipo_pessoa_0").attr('checked', true);
	}	
	
	if($("input[name=tipo_pessoa]:checked").val() == "pessoa_fisica"){
		$(".field-pessoa_juridica").hide();
	}
	else if($("input[name=tipo_pessoa]:checked").val() == "pessoa_juridica"){
		$(".field-pessoa_fisica").hide();
	}

	// Pessoa Física
	$("#id_tipo_pessoa_0").change(function(){
		$(".field-pessoa_fisica").show();
		$(".field-pessoa_juridica").hide();
	});

	// Pessoa Jurídica
	$("#id_tipo_pessoa_1").change(function(){
		$(".field-pessoa_fisica").hide();
		$(".field-pessoa_juridica").show();
	});
})

