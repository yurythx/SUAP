jQuery(document).ready(function () {
    $('input[name="nota_avaliacao"]').click(function(){
        $('input[name="nota_avaliacao"]').each(function(){
            if (this.checked) {
                $('input[name="nota_avaliacao"] + label').addClass("clicado");
            } else {
                $(this).next("label").removeClass("clicado");
            }
        });
    });
});