jQuery(function ($) {
    const periodo = $('#id_periodo');
    const datas = $('#id_data_inicio, #id_data_final');

    function atualizarCamposPeriodo() {
        const personalizado = periodo.val() === 'personalizado';
        datas.closest('.form-row').toggle(personalizado);
        datas.prop('disabled', !personalizado);
    }

    periodo.on('change', atualizarCamposPeriodo);
    atualizarCamposPeriodo();
});
