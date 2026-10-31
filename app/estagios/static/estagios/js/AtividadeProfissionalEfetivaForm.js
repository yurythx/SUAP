$(document).ready(function(){

	exibir_esconder_campo();
    $("#id_situacao_atividade").on('change', function () {
        exibir_esconder_campo();
    });
     function exibir_esconder_campo() {
        if ($('#id_situacao_atividade').val() == 'concluida') {
            $( "fieldset" ).last().show();
        }
        else {
            $( "fieldset" ).last().hide();
        }
    }
});
