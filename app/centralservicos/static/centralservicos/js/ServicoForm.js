jQuery(document).ready(function () {

    function get_centros_atendimento_por_area(area_id) {
        request_url = '/centralservicos/get_centros_atendimento_por_area/' + area_id + '/';
        $.ajax({
            url: request_url,
            success: function(data){
                $('select[name=centros_atendimento]').empty();
                $.each(data.centros, function(key, value){
                    $('select[name=centros_atendimento]').append('<option value="' + this[0] + '">' + this[1] +'</option>');

                });
            }
        });
    }
    

    $('select#id_area').on('change', function(){
        var id_area = $(this).val();
        get_centros_atendimento_por_area(id_area)
    });

});