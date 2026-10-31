function submit_form(acao){

    var justificativa = $("#justificativa_avaliacao");
    var pontuacao_validada = $("#pontuacao_validada");

    if ((acao == "indeferir" || (pontuacao_validada.val() && pontuacao_validada.val() != "")) && justificativa.val() == "") {
        alert("Para indeferir ou alterar a pontuação validada é necessário preencher a justificativa.");
        justificativa.focus();
        justificativa.css("border", "red solid 1px");
        return;
    }

    $.ajax({
        type: "POST",
        url: '/progressao_docente/salvar_avaliar_item_arquivo/' + acao + '/',
        data: $('#form_avaliacao_item').serialize(),
        success: function (retorno) {
            if(!retorno.ok){
                alert(retorno.msg);
            }else{
                if (retorno.fechar) {
                    parent.close_fancybox()
                }
            }
            if (retorno.justificar){
                $('#justificativa_avaliacao').css("border", "red solid 1px");
            }else{
                $('#justificativa_avaliacao').css("border", "#D1D1D1 solid 1px");
            }
        }
    });
}
