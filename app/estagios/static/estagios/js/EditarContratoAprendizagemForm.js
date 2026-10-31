function esconderInputObrigatoria(input){
    input.parent().parent().hide();
    input.parent().parent().removeClass("required");
}

function exibirInputObrigatoria(input) {
    input.parent().parent().show();
    input.parent().parent().addClass("required");
}

function tratarTipoEscolhido(tipo) {
    const inputArquivoDigitalizado = $( "input[type=file][name=contrato_aprendizagem]" );
    const inputDocumentoEletronico = $( "select[name=contrato_aprendizagem_documento_eletronico]" );
    if (tipo === "anexar_arquivo") {
        exibirInputObrigatoria(inputArquivoDigitalizado);
        esconderInputObrigatoria(inputDocumentoEletronico);
    }
    else if (tipo === "vincular_doc_eletronico") {
        exibirInputObrigatoria(inputDocumentoEletronico);
        esconderInputObrigatoria(inputArquivoDigitalizado);
    }
    else {
        // a estratégia escolhida foi criar o documento eletrônico
        esconderInputObrigatoria(inputArquivoDigitalizado);
        esconderInputObrigatoria(inputDocumentoEletronico);
    }
}

jQuery(document).ready(function(){
    const selectTipoContrato = $( "input[type=radio][name=estrategia_adicao_contrato]" );

    selectTipoContrato.change(function () {
        if (this.checked) {
            tratarTipoEscolhido(this.value);
        }
    });

    selectTipoContrato.each(function() {
        this.dispatchEvent(new Event("change"));
    });
});
