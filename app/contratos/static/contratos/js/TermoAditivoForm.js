
$(document).ready(function(){
	if (!$("#id_de_outro").prop("checked"))
		$("textarea[name=especificacao]").parent().parent().hide();

	$("#id_de_outro").click(function () {
		var is_checked = $(this).prop("checked");
		if (is_checked) {
            $("textarea[name=especificacao]").parent().parent().fadeIn();
            $("textarea[name=especificacao]").focus();
        }
		else
			$("textarea[name=especificacao]").parent().parent().fadeOut();
    })

})