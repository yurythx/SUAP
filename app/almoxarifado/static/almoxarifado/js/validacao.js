
/*
Este arquivo só será mantido enquando houver funções utilizando o "validate_and_submit".
O arquivo "validation.js" deve ser utilizado no lugar deste.
*/

validate_and_submit = function(validateUrl, form_selector) {
    form = $(form_selector);
    var textoOriginalBtn = $(form).find('input[type="button"]').val();
    var formSerialized = form.formSerialize().replace('csrfmiddlewaretoken=', '_crsfmiddlewaretoken=');
    
    $.ajax({
        type: "POST",
        url: validateUrl,
        data: formSerialized,
        dataType: "json",
        beforeSend: function(jqXHR){
        	element = $(form).find('input[type="button"]');
        	$(element).val('Aguarde...');
        	$(element).attr('disabled','disabled');
        },
        success: function(response) {
            if (!response.valid) {
                show_error(response);
                $(element).val(textoOriginalBtn);
        		$(element).removeAttr('disabled');
            } else {
                form.submit();
            }
        }
    });
};

show_error = function(response) {
    $("ul.messagelist").remove();
    $("main").append("<p class='errornote'></p>");
    $("p.errornote").html(response.message);
    $(":input").removeClass("invalid");
    if (!response.field_in_list) {
        $("[name="+response.field_name+"]").addClass("invalid");
    } else {
        $("[name="+response.field_name+"]:enabled:eq("+response.field_index+")").addClass("invalid");
    }
    window.scroll(0, 0);
};
