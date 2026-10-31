$(document).ready(function(){
    if($('input:radio[name=acao]:checked').val()=="3"){
        $("#id_justificativa_rejeicao").parent().parent().show();
        $("#id_tipo_arquivo").parent().parent().hide();
    }
    else {
        $("#id_justificativa_rejeicao").parent().parent().hide();
        $("#id_tipo_arquivo").parent().parent().show();
    }
    $("#id_acao_0").click(function(){
        $("#id_justificativa_rejeicao").parent().parent().hide();
        $("#id_tipo_arquivo").parent().parent().show();

    })
    $("#id_acao_1").click(function(){
        $("#id_justificativa_rejeicao").parent().parent().show();
        $("#id_tipo_arquivo").parent().parent().hide();
    })
});
