function checar_exige_eixo_tecnologico() {

    if (document.getElementById('id_exige_eixo_tecnologico').checked) {
        $('#id_ch_min_pd').parent().hide();
        $('#id_ch_max_pd').parent().hide();
        $('#id_ch_min_pd').val('0');
        $('#id_ch_max_pd').val('0');
    }else{
        $('#id_ch_min_pd').parent().show();
        $('#id_ch_max_pd').parent().show();
    }
}

jQuery(function () {

    $('#id_exige_eixo_tecnologico').click(function () {
        checar_exige_eixo_tecnologico();
    });

    checar_exige_eixo_tecnologico();
});
