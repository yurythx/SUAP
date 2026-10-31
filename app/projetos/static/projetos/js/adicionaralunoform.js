$(document).ready(function() {
    $('#id_nivel_ensino').parent().parent().hide();
    $('#id_obs').parent().parent().hide();
	$("#id_indicar_pessoa_posteriormente").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {
    if ($('#id_indicar_pessoa_posteriormente').is(':checked')) {
       $("select[name='aluno']").parent().parent().hide();
       $('#id_data').parent().parent().hide();
       $('#id_nivel_ensino').parent().parent().show();
       $('#id_obs').parent().parent().show();
    } else {
        $("select[name='aluno']").parent().parent().show();
        $('#id_data').parent().parent().show();
        $('#id_nivel_ensino').parent().parent().hide();
        $('#id_obs').parent().parent().hide();
    }
}
