$(document).ready(function(){
    change_sala();
    $("#id_sala").on('change', function() {
        change_sala();
    });
});

function change_sala(){
    var sala_id = $("#id_sala").val();
    if(sala_id){
        $.get("/comum/sala/agenda_atual/"+sala_id+"/", function(data) {
            $("#agenda_atual").html(data);
        });
        $.get("/comum/sala/informacoes_complementares/"+sala_id+"/", function(data) {
            if($("#informacoes_complementares").length === 0){
                $("#id_sala").parent().append('<div id="informacoes_complementares" class="help"><pre class="texto"></pre></div>');
            }
            $("#informacoes_complementares pre").html(data);
        });
    } else {
        $("#agenda_atual").html('');
        $("#informacoes_complementares pre").html('');
    }
}
