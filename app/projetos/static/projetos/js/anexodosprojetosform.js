$(document).ready(function() {
	$("select[name='anexoedital']").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {
    var conteudo = $("select[name='anexoedital'] option:last-child").html();
    var nome = conteudo.split(":");
    $("#id_nome").val(nome[0]);
    $("#id_descricao").val(nome[1]);

}