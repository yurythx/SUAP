$(document).ready(function() {

    $('#id_justificativa_capa').parent().parent().hide();
    $('#id_justificativa_miolo').parent().parent().hide();
    $('#id_justificativa_capa_impresso').parent().parent().hide();
    $('#id_justificativa_miolo_impresso').parent().parent().hide();

	$("#id_diagramacao_capa_aprovada").on('change', function () {
        if ($(this).val() == 'Sim') {
        $('#id_justificativa_capa').parent().parent().hide();
    } else {
        $('#id_justificativa_capa').parent().parent().show();
    }
    });

    $("#id_diagramacao_miolo_aprovada").on('change', function () {
        if ($(this).val() == 'Sim') {
        $('#id_justificativa_miolo').parent().parent().hide();
    } else {
        $('#id_justificativa_miolo').parent().parent().show();
    }
    });

    $("#id_diagramacao_capa_aprovada_impresso").on('change', function () {
        if ($(this).val() == 'Sim') {
        $('#id_justificativa_capa_impresso').parent().parent().hide();
    } else {
        $('#id_justificativa_capa_impresso').parent().parent().show();
    }
    });

    $("#id_diagramacao_miolo_aprovada_impresso").on('change', function () {
        if ($(this).val() == 'Sim') {
        $('#id_justificativa_miolo_impresso').parent().parent().hide();
    } else {
        $('#id_justificativa_miolo_impresso').parent().parent().show();
    }
    });

});


