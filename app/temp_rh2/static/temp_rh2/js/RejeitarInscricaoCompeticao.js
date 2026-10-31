$(document).ready(function(){
    if($('input:radio[name=situacao]:checked').val()=="4"){
        $("#id_observacao_rejeicao").parent().parent().show();
    }
    else {
        $("#id_observacao_rejeicao").parent().parent().hide();
    }
    $("#id_situacao_0").click(function(){
        $("#id_observacao_rejeicao").parent().parent().hide();

    })
    $("#id_situacao_1").click(function(){
        $("#id_observacao_rejeicao").parent().parent().show();
    })
});
