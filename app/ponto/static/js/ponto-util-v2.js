function get_hora_min_seg(segundos) {
    var t_horas = Math.trunc(segundos / 3600);
    var aux = segundos % 3600;
    var t_minutos = Math.trunc(aux / 60);
    var t_segundos = aux % 60;
    return [t_horas, t_minutos, t_segundos];
}

function formata_segundos(segundos, hora_min_seg_com_dois_digitos) {
    var h_m_s = get_hora_min_seg(segundos);
    var result = '';
    if (h_m_s[0] !== 0) {
        if (hora_min_seg_com_dois_digitos === true && h_m_s[0] <= 9)
            result += '0';
        result += h_m_s[0] + "h ";
    }
    if (h_m_s[1] !== 0){
        if (hora_min_seg_com_dois_digitos === true && h_m_s[1] <= 9)
            result += '0';
        result += h_m_s[1] + "min ";
    }
    if (h_m_s[2] !== 0){
        if (hora_min_seg_com_dois_digitos === true && h_m_s[2] <= 9)
            result += '0';
        result += h_m_s[2] + "seg ";
    }
    result = result.trim();
    if (result.length === 0){
        if (hora_min_seg_com_dois_digitos === true)
            result += '0';
        result += '0h';
    }
    return result
}

function get_dia_mes_ano(aaaammdd){
    // 01234567
    // aaaammdd
    var ano = aaaammdd.substr(0, 4);
    var mes = aaaammdd.substr(4, 2);
    var dia = aaaammdd.substr(6, 2);
    //
    return [dia, mes, ano];
}

$(document).ready(function () {
    $('#btn_periodo_compensacao_inverter').click(function() {
        let el_saldo_di = $('#id_saldo_data_inicio');
        let el_saldo_df = $('#id_saldo_data_fim');
        let el_debito_di = $('#id_debito_data_inicio');
        let el_debito_df = $('#id_debito_data_fim');

        if ($(el_saldo_di).val()) {
            $(el_debito_di).val($(el_saldo_di).val());
            $(el_debito_df).val($(el_saldo_df).val());
            $(el_saldo_di).val("");
            $(el_saldo_df).val("");
        } else if ($(el_debito_di).val()) {
            $(el_saldo_di).val($(el_debito_di).val());
            $(el_saldo_df).val($(el_debito_df).val());
            $(el_debito_di).val("");
            $(el_debito_df).val("");        
        }
    });
    
    $('#btn_periodo_compensacao_limpar').click(function() {
        let el_saldo_di = $('#id_saldo_data_inicio');
        let el_saldo_df = $('#id_saldo_data_fim');
        let el_debito_di = $('#id_debito_data_inicio');
        let el_debito_df = $('#id_debito_data_fim');

        $(el_saldo_di).val("");
        $(el_saldo_df).val("");
        $(el_debito_di).val("");
        $(el_debito_df).val("");        
    });    
});
