jQuery(function () {
    $('fieldset').each(function () {
        if ($(this).find('input[type=hidden]').length == 3) $(this).hide()
    });
});
