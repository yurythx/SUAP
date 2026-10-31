$(document).ready(function() {
    exibir_esconder_campo();
	$("select[name='titularidade']").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {
    if ($("select[name='titularidade']").val() == '2') {
       $("#id_0").val(100.0);
       $("#id_0").attr('readonly', 'readonly');
       contador = 1
       while (contador <= $("#id_qtd").val()){
        $("#id_"+contador).attr('readonly', 'readonly');
        $("#id_"+contador).val(0);
        $("#id_"+contador).parent().parent().prop("required", false);
        $("#id_"+contador).parent().parent().removeClass("required");
        $("select[name='"+contador+"_parceiro']").attr('readonly', 'readonly');
        $("select[name='"+contador+"_parceiro']").val('');
        $("select[name='"+contador+"_parceiro']").empty();
        $("select[name='"+contador+"_parceiro']").parent().parent().removeClass("required");
        $("select[name='"+contador+"_parceiro']").parent().prop("required", false);
        contador += 1;
       }

    } else  {
       contador = 0
       while (contador <= $("#id_qtd").val()){
           $("#id_"+contador).removeAttr('readonly');
           $("#id_"+contador).parent().prop("required", true);
           $("#id_"+contador).parent().parent().addClass("required");
           contador += 1
       }
    }
}
