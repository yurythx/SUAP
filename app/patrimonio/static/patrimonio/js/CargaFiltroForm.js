/**
 * @author dennel
 */

$(document).ready(function(){
    
    $("#id_campus").change(function(){  
        form = $("form[name=formUO]");
        form.submit();
    })
    $("#id_descricao").keyup(function(e){
    	if(e.keyCode == 13){
        	form = $("form[name=formUO]");
        	form.submit();
        }
    })
    $("#id_numero").keyup(function(e){
    	if(e.keyCode == 13){
        	form = $("form[name=formUO]");
            form.submit();
        }
    })
})
