$(document).ready(function(){

	if ($('#id_estudou_com_bolsa_integral').val() == 'True') {
        $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().show();
        $('#id_comprovante_estudou_com_bolsa_integral').parent().addClass("required");
        $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().prop("required", true);
    } else {
        $('#id_comprovante_estudou_com_bolsa_integral').val("").trigger("change");
        $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().hide();
        $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().prop("required", false);
        $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().removeClass("required");
	}
	if ($('#id_morou_em_orfanato').val() == 'Não, nunca morei' || $('#id_morou_em_orfanato').val() == '') {
        $('#id_comprovante_orfanato').val("").trigger("change");
        $('#id_comprovante_orfanato').parent().parent().parent().hide();
        $('#id_comprovante_orfanato').parent().parent().parent().prop("required", false);
        $('#id_comprovante_orfanato').parent().parent().parent().removeClass("required");
   } else {
        $('#id_comprovante_orfanato').parent().parent().parent().show();
        $('#id_comprovante_orfanato').parent().parent().parent().addClass("required");
        $('#id_comprovante_orfanato').parent().parent().prop("required", true);
   }
	exibir_esconder_campo();
	$("select[name='estudou_com_bolsa_integral']").on('change', function () {
        exibir_esconder_campo();
    });
    $("select[name='eh_refugiado']").on('change', function () {
        exibir_esconder_campo();
    });
    $("select[name='morou_em_orfanato']").on('change', function () {
        exibir_esconder_campo();
    });

    function exibir_esconder_campo() {
       if ($('#id_estudou_com_bolsa_integral').val() == 'True') {
            $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().show();
            $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().addClass("required");
            $('#id_comprovante_estudou_com_bolsa_integral').parent().prop("required", true);
       } else {
            $('#id_comprovante_estudou_com_bolsa_integral').val("").trigger("change");
            $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().hide();
            $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().prop("required", false);
            $('#id_comprovante_estudou_com_bolsa_integral').parent().parent().removeClass("required");
       }
       if ($('#id_eh_refugiado').val() == 'True') {
            $('#id_comprovante_refugiado').parent().parent().parent().show();
            $('#id_comprovante_refugiado').parent().parent().parent().addClass("required");
            $('#id_comprovante_refugiado').parent().parent().prop("required", true);
       } else {
            $('#id_comprovante_refugiado').val("").trigger("change");
            $('#id_comprovante_refugiado').parent().parent().parent().hide();
            $('#id_comprovante_refugiado').parent().parent().parent().prop("required", false);
            $('#id_comprovante_refugiado').parent().parent().parent().removeClass("required");
       }

       if ($('#id_morou_em_orfanato').val() == 'Não, nunca morei' || $('#id_morou_em_orfanato').val() == '') {
            $('#id_comprovante_orfanato').val("").trigger("change");
            $('#id_comprovante_orfanato').parent().parent().parent().hide();
            $('#id_comprovante_orfanato').parent().parent().parent().prop("required", false);
            $('#id_comprovante_orfanato').parent().parent().parent().removeClass("required");
       } else {
            $('#id_comprovante_orfanato').parent().parent().parent().show();
            $('#id_comprovante_orfanato').parent().parent().parent().addClass("required");
            $('#id_comprovante_orfanato').parent().parent().prop("required", true);
            if ($('#id_morou_em_orfanato').val() == 'Sim, moro atualmente'){
                $('#id_comprovante_orfanato').parent().parent().parent().find('p').eq(2).html('Anexar declaração da instituição.');
            } else if ($('#id_morou_em_orfanato').val() == 'Sim, já morei e FUI adotado antes de sair'){
                $('#id_comprovante_orfanato').parent().parent().parent().find('p').eq(2).html('Anexar documento comprobatório da adoção.');
            } else {
                $('#id_comprovante_orfanato').parent().parent().parent().find('p').eq(2).html('Anexar declaração específica para esse caso constante nos anexos do edital.');
            }

       }
    }
});
