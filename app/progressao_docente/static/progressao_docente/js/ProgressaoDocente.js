// SALVA ITEM DA AVALIAÇÃO (TESTAR)
function save_item(obj, url){
    var nova_url = url + obj.getAttribute("suap_id_item") + "/" + obj.getAttribute("suap_id_avaliacao") + "/" + obj.value + "/save/"
    $.ajax({
        type: "GET",
        url: nova_url,
        success: function (retorno) {
            if (!retorno.ok) {
                alert(retorno.msg);
            }
            $("#pontuacao_criterio_"+retorno.criterio).html(retorno.total)
            if (retorno.eh_aluno == true){
                $("#pontuacao_criterio_"+retorno.criterio).html(retorno.total_discente)
            }
            $("#media_criterio_"+retorno.criterio).html(retorno.media_criterio)
            $("#pontuacao_consideracao_positiva_"+retorno.criterio).html(retorno.pontuacao_consideracao_positiva)

        },
        error: function (xhr, status, err) {
            // xhr.status = 403, 404, 500 etc.
            switch (xhr.status) {
                case 403:
                    alert("403 – Problema de permissão. Tente sair do suap e entrar novamente para que suas permissões sejam atualizadas.");
                    break;
                case 404:
                    alert("404 – Recurso não encontrado.");
                    break;
                default:
                    alert("Erro " + xhr.status + " – " + (err || "Ocorreu um erro inesperado. Tente sair do suap e entrar novamente. Caso o erro persista, informe o erro para que possamos analisar."));
            }
        }
    });
}

// FINALIZAR A REAVALIAÇÃO
function finalizar_reavaliacao(id){
    var nova_url = "/progressao_docente/avaliacao/" + id + "/concluir_reavaliar/"
    $.ajax({
        type: "POST",
        url: nova_url,
        data: $('#form-reavaliacao').serialize(),
        success: function (retorno) {
            if (!retorno.ok) {
                alert(retorno.msg);
            }else{
                location.href = retorno.href
            }
        }
    });
}
