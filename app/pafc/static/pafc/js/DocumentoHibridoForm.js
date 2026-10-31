function esconderInputObrigatoria(input){
    input.parent().parent().hide();
    input.parent().parent().removeClass("required");
}

function exibirInputObrigatoria(input) {
    input.parent().parent().show();
    input.parent().parent().addClass("required");
}

function tratarTipoDocumentoEscolhido(tipo_documento) {
    const inputDocumentoEletronico = $("select[name=id_documento_eletronico]")
    const inputIdentificadorArquivo = $("input[type=text][name=identificador_arquivo]")
    const inputAssuntoArquivo = $("input[type=text][name=assunto_arquivo]")
    const inputArquivo = $("input[type=file][name=arquivo]")

    if (tipo_documento === "doc_eletronico") {
        // Exibir campo do documento eletrônico
        exibirInputObrigatoria(inputDocumentoEletronico);

        // Esconder campos do upload do arquivo
        [
            inputIdentificadorArquivo,
            inputAssuntoArquivo,
            inputArquivo,
        ].forEach(esconderInputObrigatoria);
    }
    else if (tipo_documento === "arquivo") {
        // Esconder campo do documento eletrônico
        esconderInputObrigatoria(inputDocumentoEletronico);

        // Exibir campos do upload do arquivo
        [
            inputIdentificadorArquivo,
            inputAssuntoArquivo,
            inputArquivo,
        ].forEach(exibirInputObrigatoria);
    }
}


jQuery(function () {
    const selectTipoDocumento = $("input[type=radio][name=tipo_documento]");

    selectTipoDocumento.change(function () {
        if (this.checked) {
            tratarTipoDocumentoEscolhido(this.value);
        }
    });

    selectTipoDocumento.each(function() {
        this.dispatchEvent(new Event("change"));
    });
});
