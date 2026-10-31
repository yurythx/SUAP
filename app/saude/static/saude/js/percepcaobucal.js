$(document).ready(function(){

    exibir_esconder_campo();

    $("#id_foi_dentista_anteriormente").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_usa_fio_dental").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_usa_aparelho_ortodontico").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldades").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_sorrir").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_falar").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_comer").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_relacionar").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_humor").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_estudar_trabalhar").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_higienizar").on('change', function () {
        exibir_esconder_campo();
    });

    $("#id_dificuldade_dormir").on('change', function () {
        exibir_esconder_campo();
    });


});


function exibir_esconder_campo() {
    if ($('#id_foi_dentista_anteriormente').val() == 'True') {
        $('#id_tempo_ultima_vez_dentista').parent().show();
        $("#id_tempo_ultima_vez_dentista").parent().addClass('required');
    } else {
        $('#id_tempo_ultima_vez_dentista').parent().hide();
        $("#id_tempo_ultima_vez_dentista").parent().removeClass('required');
        $("#id_tempo_ultima_vez_dentista").val('');
    }
    if ($('#id_usa_fio_dental').val() == 'True') {
        $('#id_qts_dias_fio_dental_ultima_semana').parent().show();
        $("#id_qts_dias_fio_dental_ultima_semana").parent().addClass('required');
    } else {
        $('#id_qts_dias_fio_dental_ultima_semana').parent().hide();
        $("#id_qts_dias_fio_dental_ultima_semana").parent().removeClass('required');
        $("#id_qts_dias_fio_dental_ultima_semana").val('');
    }

    if ($('#id_usa_aparelho_ortodontico').val() == 'True') {
        $('#id_tempo_ortodontia').parent().show();
        $("#id_tempo_ortodontia").parent().addClass('required');
    } else {
        $('#id_tempo_ortodontia').parent().hide();
        $("#id_tempo_ortodontia").parent().removeClass('required');
        $("#id_tempo_ortodontia").val('');
    }

    if ($('#id_dificuldades').val() == 'True') {
        $('#id_dificuldade_sorrir').parent().show();
        $("#id_dificuldade_sorrir").parent().addClass('required');
        $('#id_dificuldade_falar').parent().show();
        $("#id_dificuldade_falar").parent().addClass('required');
        $('#id_dificuldade_comer').parent().show();
        $("#id_dificuldade_comer").parent().addClass('required');
        $('#id_dificuldade_relacionar').parent().show();
        $("#id_dificuldade_relacionar").parent().addClass('required');
        $('#id_dificuldade_humor').parent().show();
        $("#id_dificuldade_humor").parent().addClass('required');
        $('#id_dificuldade_estudar_trabalhar').parent().show();
        $("#id_dificuldade_estudar_trabalhar").parent().addClass('required');
        $('#id_dificuldade_higienizar').parent().show();
        $("#id_dificuldade_higienizar").parent().addClass('required');
        $('#id_dificuldade_dormir').parent().show();
        $("#id_dificuldade_dormir").parent().addClass('required');

    } else {
        $('#id_dificuldade_sorrir').parent().hide();
        $("#id_dificuldade_sorrir").val('');
        $("#id_dificuldade_sorrir").parent().removeClass('required');
        $('#id_motivo_dificuldade_sorrir').parent().hide();
        $("#id_motivo_dificuldade_sorrir").val('');
        $("#id_motivo_dificuldade_sorrir").parent().removeClass('required');
        $('#id_dificuldade_falar').parent().hide();
        $("#id_dificuldade_falar").val('');
        $("#id_dificuldade_falar").parent().removeClass('required');
        $('#id_motivo_dificuldade_falar').parent().hide();
        $("#id_motivo_dificuldade_falar").val('');
        $("#id_motivo_dificuldade_falar").parent().removeClass('required');
        $('#id_dificuldade_comer').parent().hide();
        $("#id_dificuldade_comer").val('');
        $("#id_dificuldade_comer").parent().removeClass('required');
        $('#id_motivo_dificuldade_comer').parent().hide();
        $("#id_motivo_dificuldade_comer").val('');
        $("#id_motivo_dificuldade_comer").parent().removeClass('required');
        $('#id_dificuldade_relacionar').parent().hide();
        $("#id_dificuldade_relacionar").val('');
        $("#id_dificuldade_relacionar").parent().removeClass('required');
        $('#id_motivo_dificuldade_relacionar').parent().hide();
        $("#id_motivo_dificuldade_relacionar").val('');
        $("#id_motivo_dificuldade_relacionar").parent().removeClass('required');
        $('#id_dificuldade_humor').parent().hide();
        $("#id_dificuldade_humor").val('');
        $("#id_dificuldade_humor").parent().removeClass('required');
        $('#id_motivo_dificuldade_manter_humor').parent().hide();
        $("#id_motivo_dificuldade_manter_humor").val('');
        $("#id_motivo_dificuldade_manter_humor").parent().removeClass('required');
        $('#id_dificuldade_humor').parent().hide();
        $("#id_dificuldade_humor").val('');
        $("#id_dificuldade_humor").parent().removeClass('required');
        $('#id_motivo_dificuldade_manter_humor').parent().hide();
        $("#id_motivo_dificuldade_manter_humor").val('');
        $("#id_motivo_dificuldade_manter_humor").parent().removeClass('required');
        $('#id_dificuldade_estudar_trabalhar').parent().hide();
        $("#id_dificuldade_estudar_trabalhar").val('');
        $("#id_dificuldade_estudar_trabalhar").parent().removeClass('required');
        $('#id_motivo_dificuldade_estudar_trabalhar').parent().hide();
        $("#id_motivo_dificuldade_estudar_trabalhar").val('');
        $("#id_motivo_dificuldade_estudar_trabalhar").parent().removeClass('required');
        $('#id_dificuldade_higienizar').parent().hide();
        $("#id_dificuldade_higienizar").val('');
        $("#id_dificuldade_higienizar").parent().removeClass('required');
        $('#id_motivo_dificuldade_higienizar').parent().hide();
        $("#id_motivo_dificuldade_higienizar").val('');
        $("#id_motivo_dificuldade_higienizar").parent().removeClass('required');
        $('#id_dificuldade_dormir').parent().hide();
        $("#id_dificuldade_dormir").val('');
        $("#id_dificuldade_dormir").parent().removeClass('required');
        $('#id_motivo_dificuldade_dormir').parent().hide();
        $("#id_motivo_dificuldade_dormir").val('');
        $("#id_motivo_dificuldade_dormir").parent().removeClass('required');

    }

    if ($('#id_dificuldade_sorrir').val() == 'True') {
        $('#id_motivo_dificuldade_sorrir').parent().show();
        $("#id_motivo_dificuldade_sorrir").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_sorrir').parent().hide();
        $("#id_motivo_dificuldade_sorrir").val('');
        $("#id_motivo_dificuldade_sorrir").parent().removeClass('required');

    }

    if ($('#id_dificuldade_falar').val() == 'True') {
        $('#id_motivo_dificuldade_falar').parent().show();
        $("#id_motivo_dificuldade_falar").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_falar').parent().hide();
        $("#id_motivo_dificuldade_falar").val('');
        $("#id_motivo_dificuldade_falar").parent().removeClass('required');

    }

    if ($('#id_dificuldade_comer').val() == 'True') {
        $('#id_motivo_dificuldade_comer').parent().show();
        $("#id_motivo_dificuldade_comer").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_comer').parent().hide();
        $("#id_motivo_dificuldade_comer").val('');
        $("#id_motivo_dificuldade_comer").parent().removeClass('required');

    }

    if ($('#id_dificuldade_relacionar').val() == 'True') {
        $('#id_motivo_dificuldade_relacionar').parent().show();
        $("#id_motivo_dificuldade_relacionar").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_relacionar').parent().hide();
        $("#id_motivo_dificuldade_relacionar").val('');
        $("#id_motivo_dificuldade_relacionar").parent().removeClass('required');

    }

    if ($('#id_dificuldade_humor').val() == 'True') {
        $('#id_motivo_dificuldade_manter_humor').parent().show();
        $("#id_motivo_dificuldade_manter_humor").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_manter_humor').parent().hide();
        $("#id_motivo_dificuldade_manter_humor").val('');
        $("#id_motivo_dificuldade_manter_humor").parent().removeClass('required');

    }

    if ($('#id_dificuldade_estudar_trabalhar').val() == 'True') {
        $('#id_motivo_dificuldade_estudar_trabalhar').parent().show();
        $("#id_motivo_dificuldade_estudar_trabalhar").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_estudar_trabalhar').parent().hide();
        $("#id_motivo_dificuldade_estudar_trabalhar").val('');
        $("#id_motivo_dificuldade_estudar_trabalhar").parent().removeClass('required');

    }

    if ($('#id_dificuldade_higienizar').val() == 'True') {
        $('#id_motivo_dificuldade_higienizar').parent().show();
        $("#id_motivo_dificuldade_higienizar").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_higienizar').parent().hide();
        $("#id_motivo_dificuldade_higienizar").val('');
        $("#id_motivo_dificuldade_higienizar").parent().removeClass('required');

    }

    if ($('#id_dificuldade_dormir').val() == 'True') {
        $('#id_motivo_dificuldade_dormir').parent().show();
        $("#id_motivo_dificuldade_dormir").parent().addClass('required');

    } else {
        $('#id_motivo_dificuldade_dormir').parent().hide();
        $("#id_motivo_dificuldade_dormir").val('');
        $("#id_motivo_dificuldade_dormir").parent().removeClass('required');

    }

}
