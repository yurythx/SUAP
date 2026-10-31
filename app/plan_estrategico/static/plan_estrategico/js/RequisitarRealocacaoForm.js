$(document).ready(function(){

	if($("input[name=tipo_realocacao]:checked").val() == undefined){
		$("#id_tipo_realocacao_0").attr('checked', true);
	}

	if($("input[name=tipo_realocacao]:checked").val() == "ua_concedente"){
		$(".form-row.unidade_concedente").show();
		$(".form-row.unidade_recebedora").hide();
		$(".form-row.atividade_concedente").show();
		$(".form-row.atividade_recebedora").hide();
	}
	else if($("input[name=tipo_realocacao]:checked").val() == "ua_recebedora"){
		$(".form-row.unidade_concedente").hide();
		$(".form-row.unidade_recebedora").show();
		$(".form-row.atividade_concedente").hide();
		$(".form-row.atividade_recebedora").show();
	}
	else if($("input[name=tipo_realocacao]:checked").val() == "ambas"){
		$(".form-row.unidade_concedente").show();
		$(".form-row.unidade_recebedora").show();
		$(".form-row.atividade_concedente").show();
		$(".form-row.atividade_recebedora").show();
	}

	// Unidade Concedente
	$("#id_tipo_realocacao_0").change(function(){
		$(".form-row.unidade_concedente").show();
		$(".form-row.unidade_recebedora").hide();
		$(".form-row.atividade_concedente").show();
		$(".form-row.atividade_recebedora").hide();
	});

	// Unidade Recebedora
	$("#id_tipo_realocacao_1").change(function(){
		$(".form-row.unidade_concedente").hide();
		$(".form-row.unidade_recebedora").show();
		$(".form-row.atividade_concedente").hide();
		$(".form-row.atividade_recebedora").show();
	});

	// Ambas
	$("#id_tipo_realocacao_2").change(function(){
		$(".form-row.unidade_concedente").show();
		$(".form-row.unidade_recebedora").show();
		$(".form-row.atividade_concedente").show();
		$(".form-row.atividade_recebedora").show();
	});
})
