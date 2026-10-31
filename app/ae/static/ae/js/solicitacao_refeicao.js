$(document).ready(function(){
    function toggle_tipo(){
		$.ajax({
			method: "GET",
			url: "/ae/busca_tipo_refeicao/",
            data: { "tipo_refeicao_escolhido": $("#id_tipo_refeicao_escolhido").val()},
            success: function(result, textStatus, jqXHR) {
                $('select[name=dia_solicitacao]').find('option').remove();

                if (result[0].dia_selecionado == 'hoje_e_amanha'){
                    $('select[name=dia_solicitacao]').append($('<option value="">-------</option>'));
                    $('select[name=dia_solicitacao]').append($('<option value="1">'+$("#id_data_hoje").val()+'</option>'));
                    $('select[name=dia_solicitacao]').append($('<option value="2">'+$("#id_data_amanha").val()+'</option>'));
                } else if (result[0].dia_selecionado == 'hoje'){
                    $('select[name=dia_solicitacao]').append($('<option value="1">'+$("#id_data_hoje").val()+'</option>'));
                } else if (result[0].dia_selecionado == 'amanha'){
                    $('select[name=dia_solicitacao]').append($('<option value="2">'+$("#id_data_amanha").val()+'</option>'));
                } else{
                    $('select[name=dia_solicitacao]').append($('<option value="">Não há horário disponível</option>'));
                }
            },
            error: function() {
                $('select[name=dia_solicitacao]').find('option').remove();
                $('select[name=dia_solicitacao]').append($('<option value="">Escolha o tipo da refeição</option>'));
            }
        });
    }
	$('#id_tipo_refeicao_escolhido').on('change', toggle_tipo);
    toggle_tipo();
});
