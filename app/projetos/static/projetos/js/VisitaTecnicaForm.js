function preencherDadosConcedente(idConcedente) {
    $.ajax({
		method: "GET",
		url: `/projetos/get_json_dados_empresa/?cnpj=${idConcedente}`,
		success: function(dadosConcedente, textStatus, jqXHR) {
            if (dadosConcedente.cidade_id) {
                $( "#id_instituicao_visitada" ).val(dadosConcedente.nome);
                $( "#id_nome_contato" ).val(dadosConcedente.nome_contato);
                $( "#id_telefone_contato" ).val(dadosConcedente.telefone_contato);
                $( "#id_email_contato" ).val(dadosConcedente.email_contato);
                $( "#id_estado" ).val(dadosConcedente.estado_sigla);
                $( "#id_estado" ).trigger('change');
                $( "#id_municipio" ).val(dadosConcedente.cidade_id);
                $( "#id_logradouro" ).val(dadosConcedente.logradouro);
                $( "#id_numero" ).val(dadosConcedente.numero);
                $( "#id_bairro" ).val(dadosConcedente.bairro);
                $( "#id_complemento" ).val(dadosConcedente.complemento);
                $( "#id_cep" ).val(dadosConcedente.cep);
            }

		},
		error: function() {
            console.log("Erro ao baixar dados da concedente.");
		}
	});
}



jQuery(document).ready(function(){
    $("#id_cnpj").keyup(function() {
        if (this.value.length == 18){
            preencherDadosConcedente(this.value);
        }
    });
});
