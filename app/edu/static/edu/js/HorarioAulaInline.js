jQuery(function () {
    function mascararCampos() {
        $.each($('.field-inicio input'), function () {$(this).mask("99:99", {placeholder:" "});});
        $.each($('.field-termino input'), function () {$(this).mask("99:99", {placeholder:" "});});
    };

    $('.add-row a').click(function (e) {
        mascararCampos();
    });
});