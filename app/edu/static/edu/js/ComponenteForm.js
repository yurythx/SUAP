function checar_descricao() {
    $('#id_descricao_historico').val($('#id_descricao').val());
}

jQuery(function () {

    $('#id_descricao').keyup(function () {
        checar_descricao();
    });

});
