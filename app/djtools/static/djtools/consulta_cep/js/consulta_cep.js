$(document).ready(function () {
    $("#id_cep").blur(function () {
        // Remove tudo o que não é número para fazer a pesquisa
        var cep = this.value.replace(/[^0-9]/, "");

        // Validação do CEP; caso o CEP não possua 8 números, então cancela a consulta
        if (cep.length != 8) {
            return false;
        }

        var url = "/djtools/consulta_cep_govbr/" + cep + "/";

        $.getJSON(url, function (dadosRetorno) {
            try {
                // Preenche os campos de acordo com o retorno da pesquisa
                $("#id_endereco").val(dadosRetorno.endereco);
                $("#id_bairro").val(dadosRetorno.bairro);
                $("#id_cidade").val(dadosRetorno.codigoIBGE);
                $("#id_municipio").val(dadosRetorno.codigoIBGE);
                $("#id_endereco_uf").val(dadosRetorno.uf);
                $("#id_complemento").val(dadosRetorno.complemento);
            } catch (ex) {
            }
        });
    });
});

