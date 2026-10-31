function insertParam(key, value, removeparams)
{
    if(typeof removeparams === 'undefined'){
        removeparams = [];
    } else{
        removeparams = removeparams.split(',');
    }
    var key = encodeURIComponent(key);
    var value = encodeURIComponent(value);
    var kvp = document.location.search.substr(1).split('&');
    if (kvp == '') {
        document.location.search = '?' + key + '=' + value;
    }
    else {

        var i = kvp.length; var x; while (i--) {
            x = kvp[i].split('=');

            if (x[0] == key) {
                x[1] = value;
                kvp[i] = x.join('=');
                break;
            }
            var j = removeparams.length;
            while(j--){
                if (x[0] == removeparams[j]) {
                    x[1] = '';
                    kvp[i] = x.join('=');
                }
            }
        }

        if (i < 0) { kvp[kvp.length] = [key, value].join('='); }

        //this will reload the page, it's likely better to store this until finished
        document.location.search = kvp.join('&');
    }
}
function removeParam(parameter)
{
    var url = document.location.href;
    var urlparts= url.split('?');

    if (urlparts.length>=2)
    {
        var urlBase=urlparts.shift(); //get first part, and remove from array
        var queryString=urlparts.join("?"); //join it back up

        var prefix = encodeURIComponent(parameter)+'=';
        var pars = queryString.split(/[&;]/g);
        for (var i= pars.length; i-->0;)               //reverse iteration as may be destructive
            if (pars[i].lastIndexOf(prefix, 0)!==-1)   //idiom for string.startsWith
                pars.splice(i, 1);
        url = urlBase+'?'+pars.join('&');
    }
    document.location.href = url;
}