$(function () {
    $("#id_data_consulta").on("change", function(){
        weekday = ["Domingo","Segunda-Feira","Terça-Feira","Quarta-Feira","Quinta-Feira","Sexta-Feira","Sábado"];
        semanas_permitidas = $(this).attr("weeks")
        const datas_bloqueio = eval($(this).attr("dates"))
        const valor = $(this).val()

        // apaga o span de mensagem
        if ($("#id_data_consulta").next().is("span")){
            $("#id_data_consulta").next().remove()
        }

        // mensagem de restrição de datas específicas
        datas_bloqueio.forEach(function(d, i) {
            arr = d.split("-");
            dia_selecionado = arr[2]
            mes_selecionado = arr[1]
            ano_selecionado = arr[0]
            if(d == valor){
                $("#id_data_consulta").val("");
                if ($("#id_data_consulta").next().is("span")){
                    $("#id_data_consulta").next().remove()
                }
                msg = 'A data '+ dia_selecionado +'/'+ mes_selecionado +'/' + ano_selecionado +' foi bloqueada para agendamentos!';
                $("#id_data_consulta").after("<span id='status-msg-data' class='status status-error'>" + msg + "</span>");
                return
            }
        })

        // Mensagem de restrição da semana
        weeksArray = semanas_permitidas.split(",");
        var day = new Date(valor).getUTCDay();
        if(!semanas_permitidas.includes(day)){
            this.value = '';
            if ($(this).next().is("span")){
                $(this).next().remove()
            }
            msg = 'Para esse evento, não é permitido agendamentos na '+ weekday[day] + '!'
            $(this).after("<span id='status-msg-data' class='status status-error'>" + msg + "</span>")
        }
    });
});
