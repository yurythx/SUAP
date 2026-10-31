function preencherDadosConcedente(idConcedente) {
    $.ajax({
		method: "GET",
		url: `/estagios/get_json_dados_concedente/${idConcedente}`,
		success: function(dadosConcedente, textStatus, jqXHR) {
            if (dadosConcedente.endereco && dadosConcedente.endereco.cidade) {
                const selectEstado = $("select[name=estado]")
                const estadoOption = new Option(
                    dadosConcedente.endereco.cidade.estado.nome,
                    dadosConcedente.endereco.cidade.estado.id,
                    false, false
                );
                selectEstado.append(estadoOption)
                selectEstado.val(dadosConcedente.endereco.cidade.estado.id).trigger('change');

                const selectCidade = $("select[name=cidade]")
                const cidadeOption = new Option(
                    `${dadosConcedente.endereco.cidade.nome} - ${dadosConcedente.endereco.cidade.estado.sigla}`,
                    dadosConcedente.endereco.cidade.id,
                    false, false
                );
                selectCidade.append(cidadeOption)
                selectCidade.val(dadosConcedente.endereco.cidade.id).trigger('change');
            }
            $( "#id_logradouro" ).val(dadosConcedente.endereco.logradouro);
            $( "#id_numero" ).val(dadosConcedente.endereco.numero);
            $( "#id_complemento" ).val(dadosConcedente.endereco.complemento);
            $( "#id_bairro" ).val(dadosConcedente.endereco.bairro);
            $( "#id_cep" ).val(dadosConcedente.endereco.cep);
		},
		error: function() {
            console.log("Erro ao baixar dados da concedente.");
		}
	});
}



jQuery(document).ready(function(){
    $( "select[name=empresa]" ).change(function() { preencherDadosConcedente(this.value); });
});
