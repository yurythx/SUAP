function submit_aceleracao_form(acao){
    var nova_url = "/progressao_docente/aceleracao/" + acao + "/";
    var justificativa = $("#justificativa");
    if (acao == "indeferir" && justificativa.val() == "") {
        alert("Para indeferir o arquivo é necessário preencher a justificativa.");
        justificativa.focus();
        justificativa.css("border", "red solid 1px");
        return;
    }

    if (confirm("Deseja mesmo "+ acao +" este arquivo?")) {
        $.ajax({
            type: "POST",
            url: nova_url,
            data: $('#form-aceleracao-progressao').serialize(),
            success: function (retorno) {
                if (!retorno.ok) {
                    alert(retorno.msg);
                    return;
                }
                window.scrollTo(0,0);
                window.location.reload();
            }
        });
    }
}
