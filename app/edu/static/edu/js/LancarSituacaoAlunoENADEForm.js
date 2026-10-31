jQuery(function () {
    if ($('.errorlist', 'div.justificativa_dispensa').length == 0) {
        $('div.justificativa_dispensa').hide();
    }

    if ($('#id_situacao').val() == 2) {
        $('div.justificativa_dispensa').show();
    }

    $('#id_situacao').change(function () {
        valor_selecionado = $(this).val();

        if (valor_selecionado == 2) {
            $('div.justificativa_dispensa').show();
        } else {
            $('div.justificativa_dispensa').hide();
        }
    });
});
