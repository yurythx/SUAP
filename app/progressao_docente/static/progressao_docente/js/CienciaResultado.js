$(function() {
    $("#btn_finalizar").on('click', function(e) {
        var form = $('#form-ciencia');
        console.log(form.serialize());
        // e.preventDefault();
        // return false;
        $(form).submit();
    });
});
