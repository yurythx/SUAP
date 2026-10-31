$(document).ready(function(){

	exibir_esconder_campo();

    $("#id_tipo_fomento").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_permite_colaborador_voluntario").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_forma_selecao").on('change', function () {
        exibir_esconder_campo();
    });
    if ($('#id_tipo_edital').val() == 'Extensão Contínuo') {
        $("#id_exige_etapa_avaliacao").parent().parent().show();
    }
    else {
        $("#id_exige_etapa_avaliacao").parent().parent().hide();
    }

    function exibir_esconder_campo() {

        if ($('#id_tipo_fomento').val() == 'Externo') {
    		$("#id_qtd_projetos_selecionados").parent().parent().hide();
			$("#id_forma_selecao").parent().parent().hide();
			$("#id_campus_especifico").parent().parent().hide();
			$("#id_inicio_pre_selecao").parent().parent().hide();
			$("#id_fim_pre_selecao").parent().parent().hide();
			$("#id_data_recurso_pre_selecao").parent().parent().hide();
			$("#id_inicio_selecao").parent().parent().hide();
			$("#id_fim_selecao").parent().parent().hide();
			$("#id_data_recurso").parent().parent().hide();
			$("#id_divulgacao_selecao").parent().parent().hide();
			$("#id_valor_financiado_por_projeto").parent().parent().hide();

		}
		else {
			$("#id_qtd_projetos_selecionados").parent().parent().show();
			$("#id_forma_selecao").parent().parent().show();
			$("#id_campus_especifico").parent().parent().show();
			$("#id_inicio_pre_selecao").parent().parent().show();
			$("#id_fim_pre_selecao").parent().parent().show();
			$("#id_data_recurso_pre_selecao").parent().parent().show();
			$("#id_inicio_selecao").parent().parent().show();
			$("#id_fim_selecao").parent().parent().show();
			$("#id_data_recurso").parent().parent().show();
			$("#id_divulgacao_selecao").parent().parent().show();
			$("#id_valor_financiado_por_projeto").parent().parent().show();

	 	}
	 	if ($('#id_permite_colaborador_voluntario').is(':checked')){
	 	    $('#id_colaborador_externo_bolsista').parent().parent().show();
	 	}
	 	else {
	 	    $('#id_colaborador_externo_bolsista').parent().parent().hide();
	 	    $('#id_colaborador_externo_bolsista').prop( "checked", false);
	 	}
	 	if ($('#id_forma_selecao').val() == 3) {
			$("#id_qtd_projetos_selecionados").parent().parent().show();
		}
		else {
			$("#id_qtd_projetos_selecionados").parent().parent().hide();
	 	}

    }

	$('#id_tipo_edital').on('change', function(){
    	if ($(this).val() == 4) {
	    	data = new Date();
        	ano = data.getFullYear();
			document.getElementById("id_inicio_inscricoes").value = ano+"-01-01T00:00";
	 		document.getElementById("id_fim_inscricoes").value = ano+"-12-31T00:00";
			document.getElementById("id_inicio_pre_selecao").value = ano+"-01-01T00:00";
			document.getElementById("id_fim_pre_selecao").value = ano+"-01-01T00:00";
			document.getElementById("id_data_recurso_pre_selecao").value = ano+"-01-01T00:00";
			document.getElementById("id_inicio_selecao").value = ano+"-01-01T00:00";
			document.getElementById("id_fim_selecao").value = ano+"-12-31T00:00";
			document.getElementById("id_divulgacao_selecao").value = ano+"-01-01T00:00";
			$("#id_exige_etapa_avaliacao").parent().parent().show();
	 	}
	 	else {
	 	    $("#id_exige_etapa_avaliacao").parent().parent().hide();
	 	}
	});
});
