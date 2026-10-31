$(document).ready(function(){
    function get_centros_atendimento_por_servico_e_campus(servico_id, uo_id) {
        request_url = '/centralservicos/get_centros_atendimento_por_servico_e_campus/' + servico_id + '/' + uo_id + '/';
        $.ajax({
            url: request_url,
            success: function(data){
                $('#id_centro_atendimento').html('');
                tem_centro_local = false;
                $.each(data.centros, function(key, value){
                    checked = '';
                    if (data.centros.length == 1){
                        checked = 'checked=checked';
                    }

                    $('#id_centro_atendimento').append('<li><label for="id_centro_atendimento_' + this[0] + '"><input id="id_centro_atendimento_' + this[0] + '" name="centro_atendimento" type="radio" value="'+ this[0] +'" '+ checked +' /> ' + this[1] +'</label></li>');
                    if (this[2]){
                        tem_centro_local = true;
                    }
                });
                if (data.centros == '') {
                    alert('Não é possível reclassificar este chamado neste campus, pois não existe centro de atendimento cadastrado para este serviço neste campus.');
                } else {
                    if (tem_centro_local){
                        $(".form-row.campus").show();
                    } else {
                        $(".form-row.campus").hide();
                    }
                }
            }
        });
    }

    function get_campus_com_centros_atendimento(servico_id, chamado_id) {
        if (typeof chamado_id == 'undefined'){
            chamado_id = 0;
        }
        var request_url = '/centralservicos/get_campus_com_centros_atendimento/' + servico_id + '/' + chamado_id + '/';
        $.ajax({
            url: request_url,
            success: function(data){
                $('select[name=uo]').empty();
                $.each(data.campus, function(key, value){
                    if (this[2]) {
                        $('select[name=uo]').append('<option value="' + this[0] + '" selected=\"selected\">' + this[1] +'</option>');
                    } else {
                        $('select[name=uo]').append('<option value="' + this[0] + '">' + this[1] +'</option>');
                    }

                });

                var uo_id = $('select[name=uo]').find(':selected').val();
                get_centros_atendimento_por_servico_e_campus(servico_id, uo_id);
            }
        });
    }

    var servico_id = $('select[name=uo]').attr('data-servico_id');
    var chamado_id = $('select[name=uo]').attr('data-chamado_id');
    get_campus_com_centros_atendimento(servico_id, chamado_id);


    $('select[name=uo]').change(function(){
        var uo_id = $(this).val();        
        var servico_id = $(this).attr('data-servico_id');
        get_centros_atendimento_por_servico_e_campus(servico_id, uo_id)
    });


    // Função criada para monitar mudanças em campos "hidden", uma vez que o evento "change"
    // de um campo hidden não é disparado e no caso do componente "forms.ModelPopupChoiceField"
    // não é possível se basear em nenhum outro componente para disparar o evento onchange.
    function onchange_hidden_input(selector, callback) {
       var input = $(selector);
       var oldvalue = input.val();
       setInterval(function(){
          if (input.val()!=oldvalue){
              oldvalue = input.val();
              callback();
          }
       }, 1000);
    }

    onchange_hidden_input('#id_servico', function(){
        // Se o serviço for Sistemico, não aparece uo
        // Só aparece o campus se o serviço tiver centro de atendimento local
        servico_id = $('#id_servico').val();
        get_campus_com_centros_atendimento(servico_id);
        uo_id = $('select[name=uo]').find(':selected').val();
        $('select[name=uo]').attr('data-servico_id', servico_id);
        get_centros_atendimento_por_servico_e_campus(servico_id, uo_id);
    });
});
