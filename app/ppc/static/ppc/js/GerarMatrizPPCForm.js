function checar_tipo_tramitacao() {

    if (document.getElementById('id_tipo_tramitacao_0').checked) {
        $('#id_diretorias_0').parent().parent().parent().parent().show();
        $('#id_vincular_curso').parent().parent().hide();
        $('#id_cod_outros_cursos').parent().parent().hide();
    }
    else if (document.getElementById('id_tipo_tramitacao_1').checked) {
        $('#id_vincular_curso').parent().parent().show();
        $('#id_cod_outros_cursos').parent().parent().show();
        $('#id_diretorias_0').parent().parent().parent().parent().hide();
    }
    else{
        $('#id_diretorias_0').parent().parent().parent().parent().hide();
        $('#id_vincular_curso').parent().parent().hide();
        $('#id_cod_outros_cursos').parent().parent().hide();
    }
}

jQuery(function () {

    $('#id_tipo_tramitacao').click(function () {
        checar_tipo_tramitacao();
    });

    checar_tipo_tramitacao();

});
