$(document).ready(function(){
	if ($('#id_situacao').val() == 'Desligado'){
		$("#id_razao_desligamento").parent().parent().show();
		$('label[for="id_razao_desligamento"]').addClass('required');

	}
	else {
		$("#id_razao_desligamento").parent().parent().hide();
		$('label[for="id_razao_desligamento"]').removeClass('required');
		$('#id_razao_desligamento').val('');
	}
	$('#id_situacao').on('change', function(){
        if ($(this).val() == 'Desligado') {
            $("#id_razao_desligamento").parent().parent().show();
            $('label[for="id_razao_desligamento"]').addClass('required');
        }
        else {
            $("#id_razao_desligamento").parent().parent().hide();
            $('label[for="id_razao_desligamento"]').removeClass('required');
            $('#id_razao_desligamento').val('');
        }
    });
});
