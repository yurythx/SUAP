
function tratarAcaoEscolhida(acao) {
    const inputDocumento = $("select[name=documento_existente]")
    if (acao === "emitir") {
        inputDocumento.parent().parent().hide()
        inputDocumento.parent().removeClass("required")
    }
    else if (acao === "vincular") {
        inputDocumento.parent().parent().show()
        inputDocumento.parent().addClass("required")
    }
}


jQuery(function () {
    const selectAcao = $("input[type=radio][name=acao]");

    selectAcao.change(function () {
        if (this.checked) {
            tratarAcaoEscolhida(this.value);
        }
    });

    selectAcao.each(function() {
        this.dispatchEvent(new Event("change"));
    });
});
