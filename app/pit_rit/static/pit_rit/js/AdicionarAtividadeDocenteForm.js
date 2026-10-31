function checar_periodicidade() {
    $('input[name="qtd_dias"]').parent().hide();

    if ($('#id_periodicidade_0').length > 0 && $('#id_periodicidade_0')[0].checked) {
        $('input[name="qtd_dias"]').parent().hide().hide();
    }

    if ($('#id_periodicidade_1').length > 0 && $('#id_periodicidade_1')[0].checked) {
        $('input[name="qtd_dias"]').parent().hide().show();
    }
}


jQuery(function () {

    $('#id_periodicidade_0').click(function () {
        checar_periodicidade();
    });
    $('#id_periodicidade_1').click(function () {
        checar_periodicidade();
    });

    checar_periodicidade();
});
