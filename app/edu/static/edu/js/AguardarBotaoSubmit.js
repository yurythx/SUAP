$("input[type=submit]").on("click", function () {
    elem = $(this);
    form = $(this.form);
    elem.parent().find("input[type=submit]").attr("disabled", "disabled");
    elem.val("Aguarde...");

    if (elem.attr("name")) {
        elem.parent().append('<input type="hidden" name="' + elem.attr("name") + '" value="' + elem.val() + '" />');
    }

    form.find(".selector-chosen select[multiple] option").attr("selected", "selected");
    form.submit();
});