$(document).ready(function(){
	$("select#id_nova_jornada").unbind('change').on('change', function(){
		jornada = $(this).val();
		ch_dia = parseInt(jornada/5);
		dias = [$("#id_seg"), $("#id_ter"), $("#id_qua"), $("#id_qui"), $("#id_sex")]
		for(i=0; i<dias.length; i++){
			dias[i].val(ch_dia);
		}
		ch_restante = jornada%5;
		for(i=0; i<ch_restante; i++){
			dias[i].val(ch_dia+1);
		}
	});
});
