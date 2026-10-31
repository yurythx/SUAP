$(document).ready(function(){
	if ($('#id_tipo_edital').val() == 3 ){
		$("#id_nota_corte_projeto_fluxo_continuo").parent().parent().show();

	}
	else {
		$("#id_nota_corte_projeto_fluxo_continuo").parent().parent().hide();
	}


	if ($('#id_forma_selecao').val() == 1 ){
		$("#id_qtd_bolsa_alunos").parent().parent().hide();
		$("#id_qtd_bolsa_servidores").parent().parent().hide();
	}

	else if ($('#id_forma_selecao').val() == 2){
		$("#id_qtd_bolsa_alunos").parent().parent().show();
		$("#id_qtd_bolsa_servidores").parent().parent().show();
	}

	else{
		$("#id_qtd_bolsa_alunos").parent().parent().hide();
		$("#id_qtd_bolsa_servidores").parent().parent().hide();
	}

	$('#id_forma_selecao').on('change', function(){
		if ($(this).val() == 2) {
			$("#id_qtd_bolsa_alunos").parent().parent().show();
			$("#id_qtd_bolsa_servidores").parent().parent().show();
		}
		else {
			$("#id_qtd_bolsa_alunos").parent().parent().hide();
			$("#id_qtd_bolsa_servidores").parent().parent().hide();
	 	}
	});

	$('#id_tipo_edital').on('change', function(){
    	if ($(this).val() == 3) {
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
            $("#id_nota_corte_projeto_fluxo_continuo").parent().parent().show();
	 	}
        else {
	 		document.getElementById("id_inicio_inscricoes").value = "";
	 		document.getElementById("id_fim_inscricoes").value = "";
			document.getElementById("id_inicio_pre_selecao").value = "";
			document.getElementById("id_fim_pre_selecao").value = "";
			document.getElementById("id_data_recurso_pre_selecao").value = "";
			document.getElementById("id_inicio_selecao").value = "";
            document.getElementById("id_fim_selecao").value = "";
			document.getElementById("id_divulgacao_selecao").value = "";
            $("#id_nota_corte_projeto_fluxo_continuo").parent().parent().hide();
        }
	});
    $('#id_inicio_inscricoes').on('change', function(){
        if ($('#id_tipo_edital').val() == 3) {
	 		data = document.getElementById("id_inicio_inscricoes").value;
	 		document.getElementById("id_fim_inscricoes").value = data;
			document.getElementById("id_inicio_pre_selecao").value = data;
			document.getElementById("id_fim_pre_selecao").value = data;
			document.getElementById("id_data_recurso_pre_selecao").value = data;
			document.getElementById("id_inicio_selecao").value = data;
            document.getElementById("id_fim_selecao").value = data;
			document.getElementById("id_divulgacao_selecao").value = data;
	 	}
	});

	exibir_esconder_campo();
    $("#id_formato").on('change', function () {
        exibir_esconder_campo();
    });
    $("#id_exigir_participacao_como_avaliador").on('change', function () {
        exibir_esconder_campo();
    });

    function exibir_esconder_campo() {

    if ($('#id_formato').val() == 'Simplificado') {
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
			$("#id_qtd_maxima_alunos").parent().parent().hide();
			$("#id_qtd_maxima_alunos").parent().parent().parent().hide();
			$("#id_qtd_maxima_alunos_bolsistas").parent().parent().hide();
			$("#id_qtd_maxima_servidores").parent().parent().hide();
			$("#id_qtd_maxima_servidores_bolsistas").parent().parent().hide();
			$("#id_valor_financiado_por_projeto").parent().parent().hide();
			$("#id_qtd_anos_anteriores_publicacao").parent().parent().hide();
			$("#id_peso_avaliacao_lattes_coordenador").parent().parent().hide();
			$("#id_peso_avaliacao_projeto").parent().parent().hide();
			$("#id_nota_corte_projeto_fluxo_continuo").parent().parent().hide();
			$("#id_permite_coordenador_com_bolsa_previa").parent().parent().hide();
			$("#id_coordenador_pode_receber_bolsa").parent().parent().hide();
			$(".field-titulacoes_avaliador").hide();

		}
		else {
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
			$("#id_qtd_maxima_alunos").parent().parent().show();
			$("#id_qtd_maxima_alunos").parent().parent().parent().show();
			$("#id_qtd_maxima_alunos_bolsistas").parent().parent().show();
			$("#id_qtd_maxima_servidores").parent().parent().show();
			$("#id_qtd_maxima_servidores_bolsistas").parent().parent().show();
			$("#id_valor_financiado_por_projeto").parent().parent().show();
			$("#id_qtd_anos_anteriores_publicacao").parent().parent().show();
			$("#id_peso_avaliacao_lattes_coordenador").parent().parent().show();
			$("#id_peso_avaliacao_projeto").parent().parent().show();
			$("#id_nota_corte_projeto_fluxo_continuo").parent().parent().show();
			$("#id_permite_coordenador_com_bolsa_previa").parent().parent().show();
			$("#id_coordenador_pode_receber_bolsa").parent().parent().show();
			$(".field-titulacoes_avaliador").show();

	 	}
        if ($('#id_exigir_participacao_como_avaliador').is(':checked')) {
            $('#id_quantidade_avaliacoes').parent().parent().show();
            $('#id_anos_avaliacoes_considerar').parent().parent().show();
            $('label[for="id_quantidade_avaliacoes"]').addClass('required');
            $('label[for="id_anos_avaliacoes_considerar"]').addClass('required');
        } else {
            $('#id_quantidade_avaliacoes').parent().parent().hide();
            $('#id_anos_avaliacoes_considerar').parent().parent().hide();
            $('label[for="id_quantidade_avaliacoes"]').removeClass('required');
            $('label[for="id_anos_avaliacoes_considerar"]').removeClass('required');
            $('#id_quantidade_avaliacoes').val('');
            $('#id_anos_avaliacoes_considerar').val('');
        }
    }



});
