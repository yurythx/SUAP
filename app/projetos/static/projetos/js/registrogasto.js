$(document).ready(function(){

	exibir_esconder_campo();

    $("#id_gasto_nao_executado").on('change', function () {
        exibir_esconder_campo();
    });

    function exibir_esconder_campo() {

        if ($('#id_gasto_nao_executado').is(':checked')) {
    		$("select[name='ano']").parent().parent().hide();
			$("#id_mes").parent().parent().hide();
			$("#id_descricao").parent().parent().hide();
			$("#id_qtd").parent().parent().hide();
			$("#id_valor_unitario").parent().parent().hide();
			$("#id_arquivo").parent().parent().parent().hide();
			$("#id_cotacao_precos").parent().parent().parent().hide();

		}
		else {
			$("select[name='ano']").parent().parent().show();
			$("#id_mes").parent().parent().show();
			$("#id_descricao").parent().parent().show();
			$("#id_qtd").parent().parent().show();
			$("#id_valor_unitario").parent().parent().show();
			$("#id_arquivo").parent().parent().parent().show();
			$("#id_cotacao_precos").parent().parent().parent().show();

	 	}

    }


});
