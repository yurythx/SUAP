$(document).ready(function(){

    // Adicionar Modalidade ao Evento
    ativaTipoSubmissao($('#id_tipo_submissao').val());
    $('#id_tipo_submissao').on('change', function(){
        ativaTipoSubmissao($(this).val());
    });

    // Vincular modalidades ao Avaliador
    ativaModalidade($('#id_modalidade').val());
    $('#id_modalidade').on('change', function(){
        ativaModalidade($(this).val());
    });

});

function ativaTipoSubmissao(tipo) {
    if (tipo == 'TEX') {
        $('.form-row.tipo_limite_por_texto').show();
        $('.form-row.tipo_arquivos_permitidos').hide();
    } else if (tipo == 'ARQ') {
        $('.form-row.tipo_limite_por_texto').hide();
        $('.form-row.tipo_arquivos_permitidos').show();
    } else {
        $('.form-row.tipo_limite_por_texto').hide();
        $('.form-row.tipo_arquivos_permitidos').hide();
    }
}

function ativaModalidade(modalidade) {
    if (modalidade != '') {
        $('.form-row.areas_tematicas').show();
        get_areas_tematicas_da_modalidade(modalidade);
    } else {
        $('.form-row.areas_tematicas').hide();
    }
}

function get_areas_tematicas_da_modalidade(modalidade_id) {
    request_url = '/eventos/get_areas_tematicas_da_modalidade/' + modalidade_id + '/';
    $.ajax({
        url: request_url,
        success: function (data) {
            $('#id_areas_tematicas').html('<ul></ul>');
            $.each(data.areas_tematicas, function (key, value) {
                checked = '';
                if (data.areas_tematicas.length == 1) {
                    checked = 'checked=checked';
                }
                $('#id_areas_tematicas ul').append('<li><label for="id_areas_tematicas_' + this[0] + '"><input id="id_areas_tematicas' + this[0] + '" name="areas_tematicas" type="checkbox" value="' + this[0] + '" ' + checked + ' /> ' + this[1] + '</label></li>');
            });
        }
    });
}
