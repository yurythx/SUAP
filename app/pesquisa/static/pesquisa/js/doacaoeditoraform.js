$(document).ready(function() {
    $("#id_responsavel").parent().parent().hide();
    $("select[name='servidor']").parent().parent().hide();
	$("#id_eh_servidor").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {

    if ($('#id_eh_servidor').val() == 'True') {
       $("#id_responsavel").parent().parent().hide();
       $("#id_responsavel").parent().parent().removeClass("required");
       $("#id_responsavel").parent().prop("required", false);
       $("select[name='servidor']").parent().parent().show();
       $("select[name='servidor']").parent().parent().addClass("required");
       $("select[name='servidor']").parent().prop("required", true);
    } else  {
       $("#id_responsavel").parent().parent().show();
       $("#id_responsavel").parent().parent().addClass("required");
       $("#id_responsavel").parent().prop("required", true);
       $("select[name='servidor']").parent().parent().hide();
       $("select[name='servidor']").parent().parent().removeClass("required");
       $("select[name='servidor']").parent().prop("required", false);
    }
}
