$(document).ready(function(){
	
	if ($('#id_forma_selecao').val() == 2){
		$("#id_qtd_projetos_selecionados").parent().parent().show();
	}
		 
	else{
		$("#id_qtd_projetos_selecionados").parent().parent().hide();
	}
	 
	$('#id_forma_selecao').on('change', function(){
		if ($(this).val() == 2) {
			$("#id_qtd_projetos_selecionados").parent().parent().show();
		}
		else {
			$("#id_qtd_projetos_selecionados").parent().parent().hide();
	 	}
	});

	 
	$('#id_tipo_edital').on('change', function(){
    	if ($(this).val() == 2) {
	    	data = new Date();
        	ano = data.getFullYear();
			document.getElementById("id_inicio_inscricoes").value = ano+"-01-01T00:00";
	 		document.getElementById("id_fim_inscricoes").value = ano+"-12-31T00:00";
			document.getElementById("id_inicio_pre_selecao").value = ano+"-01-01T00:00";
			document.getElementById("id_inicio_selecao").value = ano+"-01-01T00:00";
			document.getElementById("id_fim_selecao").value = ano+"-12-31T00:00";
			document.getElementById("id_divulgacao_selecao").value = ano+"-01-01T00:00";
	 	}
	});
});
