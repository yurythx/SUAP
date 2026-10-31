$(document).ready(function() {
    exibir_esconder_campo();
	$("#id_tipo").on('change', function () {
        exibir_esconder_campo();
    });

});

function exibir_esconder_campo() {
    if ($('#id_tipo').val() == 'Publicação de Obra') {
       $('#id_data_inicio_verificacao_plagio').parent().parent().show();
       $("#id_data_inicio_verificacao_plagio").parent().parent().addClass("required");
       $("#id_data_inicio_verificacao_plagio").parent().prop("required", true);

       $('#id_data_termino_verificacao_plagio').parent().parent().show();
       $("#id_data_termino_verificacao_plagio").parent().parent().addClass("required");
       $("#id_data_termino_verificacao_plagio").parent().prop("required", true);

       $('#id_data_inicio_analise_especialista').parent().parent().show();
       $("#id_data_inicio_analise_especialista").parent().parent().addClass("required");
       $("#id_data_inicio_analise_especialista").parent().prop("required", true);

       $('#id_data_termino_analise_especialista').parent().parent().show();
       $("#id_data_termino_analise_especialista").parent().parent().addClass("required");
       $("#id_data_termino_analise_especialista").parent().prop("required", true);

       $('#id_data_inicio_validacao_conselho').parent().parent().show();
       $("#id_data_inicio_validacao_conselho").parent().parent().addClass("required");
       $("#id_data_inicio_validacao_conselho").parent().prop("required", true);

       $('#id_data_termino_validacao_conselho').parent().parent().show();
       $("#id_data_termino_validacao_conselho").parent().parent().addClass("required");
       $("#id_data_termino_validacao_conselho").parent().prop("required", true);

       $('#id_data_inicio_termos').parent().parent().show();
       $("#id_data_inicio_termos").parent().parent().addClass("required");
       $("#id_data_inicio_termos").parent().prop("required", true);

       $('#id_data_termino_termos').parent().parent().show();
       $("#id_data_termino_termos").parent().parent().addClass("required");
       $("#id_data_termino_termos").parent().prop("required", true);

       $('#id_questionario_parecerista').parent().parent().parent().show();
       $("#id_questionario_parecerista").parent().parent().parent().addClass("required");
       $("#id_questionario_parecerista").parent().parent().parent().prop("required", true);

       $("select[name='linha_editorial_old']").parent().parent().parent().parent().show();
       $("select[name='linha_editorial_old']").parent().parent().addClass("required");
       $("select[name='linha_editorial_old']").parent().prop("required", true);
       $('#id_linha_editorial').parent().prop("required", true);
       $('#id_linha_editorial').parent().parent().addClass("required");

       $('#id_instrucoes').parent().parent().parent().show();
       $("#id_instrucoes").parent().parent().parent().addClass("required");
       $("#id_instrucoes").parent().parent().parent().prop("required", true);

       $('#id_manual').parent().parent().parent().parent().show();
       $("#id_manual").parent().parent().parent().addClass("required");
       $("#id_manual").parent().parent().parent().prop("required", true);

    } else {
        $('#id_data_inicio_verificacao_plagio').parent().parent().hide();
        $("#id_data_inicio_verificacao_plagio").parent().parent().removeClass("required");
        $("#id_data_inicio_verificacao_plagio").parent().prop("required", false);

        $('#id_data_termino_verificacao_plagio').parent().parent().hide();
        $("#id_data_termino_verificacao_plagio").parent().parent().removeClass("required");
        $("#id_data_termino_verificacao_plagio").parent().prop("required", false);

        $('#id_data_inicio_analise_especialista').parent().parent().hide();
        $("#id_data_inicio_analise_especialista").parent().parent().removeClass("required");
        $("#id_data_inicio_analise_especialista").parent().prop("required", false);

        $('#id_data_termino_analise_especialista').parent().parent().hide();
        $("#id_data_termino_analise_especialista").parent().parent().removeClass("required");
        $("#id_data_termino_analise_especialista").parent().prop("required", false);

        $('#id_data_inicio_validacao_conselho').parent().parent().hide();
        $("#id_data_inicio_validacao_conselho").parent().parent().removeClass("required");
        $("#id_data_inicio_validacao_conselho").parent().prop("required", false);

        $('#id_data_termino_validacao_conselho').parent().parent().hide();
        $("#id_data_termino_validacao_conselho").parent().parent().removeClass("required");
        $("#id_data_termino_validacao_conselho").parent().prop("required", false);

        $('#id_data_inicio_termos').parent().parent().hide();
        $("#id_data_inicio_termos").parent().parent().removeClass("required");
        $("#id_data_inicio_termos").parent().prop("required", false);

        $('#id_data_termino_termos').parent().parent().hide();
        $("#id_data_termino_termos").parent().parent().removeClass("required");
        $("#id_data_termino_termos").parent().prop("required", false);

        $('#id_questionario_parecerista').parent().parent().parent().hide();
        $("#id_questionario_parecerista").parent().parent().parent().removeClass("required");
        $("#id_questionario_parecerista").parent().parent().parent().prop("required", false);

        $("select[name='linha_editorial_old']").parent().parent().parent().parent().hide();
        $("select[name='linha_editorial_old']").parent().parent().removeClass("required");
        $("select[name='linha_editorial_old']").parent().prop("required", false);
        $('#id_linha_editorial').prop("required", false);
        $('#id_linha_editorial').removeClass("required");

        $('#id_instrucoes').parent().parent().parent().hide();
        $("#id_instrucoes").parent().parent().parent().removeClass("required");
        $("#id_instrucoes").parent().parent().parent().prop("required", false);

        $('#id_manual').parent().parent().parent().parent().hide();
        $("#id_manual").parent().parent().parent().removeClass("required");
        $("#id_manual").parent().parent().parent().prop("required", false);


    }
}
