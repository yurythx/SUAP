$(document).ready(function() {
    exibir_esconder_campo();
	$("#id_eh_externo").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {
    if ($('#id_eh_externo').val() == 'True') {
       $("#id_nome").parent().parent().show();
       $("#id_nome").parent().parent().addClass("required");
       $("#id_instituicao").parent().parent().show();
       $("#id_instituicao").parent().parent().addClass("required");
       $("select[name='vinculo']").parent().parent().hide();
       $("select[name='vinculo']").parent().parent().removeClass("required");
       $("select[name='vinculo']").parent().prop("required", false);
       $("select[name='vinculo']").empty();
       $("select[name='vinculo']").val('');
    } else if ($('#id_eh_externo').val() == 'False') {
       $("#id_nome").parent().parent().hide();
       $("#id_nome").parent().parent().removeClass("required");
       $("#id_instituicao").parent().parent().hide();
       $("#id_instituicao").parent().parent().removeClass("required");
       $("select[name='vinculo']").parent().parent().show();
       $("select[name='vinculo']").parent().parent().addClass("required");
       $("select[name='vinculo']").parent().prop("required", true);
    } else  {
       $("#id_nome").parent().parent().hide();
       $("#id_nome").parent().parent().removeClass("required");
       $("#id_instituicao").parent().parent().hide();
       $("#id_instituicao").parent().parent().removeClass("required");
       $("select[name='vinculo']").parent().parent().show();
       $("select[name='vinculo']").parent().parent().addClass("required");
       $("select[name='vinculo']").parent().prop("required", true);
    }
}
