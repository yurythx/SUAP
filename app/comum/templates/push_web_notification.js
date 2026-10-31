function urlB64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
        .replace(/\-/g, "+")
        .replace(/_/g, "/");
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}
function subscribePushWebNotification(){
    if ("serviceWorker" in navigator && "PushManager" in window) {
        navigator.serviceWorker
          .getRegistration()
          .then(function (swRegistration) {
            if (swRegistration) {
              const applicationServerKey = urlB64ToUint8Array(
                "{{ vapid_public_key }}"
              );
              swRegistration.pushManager
                .subscribe({
                  userVisibleOnly: true,
                  applicationServerKey: applicationServerKey,
                })
                .then(function (subscription) {
                  console.log(subscription);
                  var subscriptionJson = JSON.stringify(subscription);
                  console.log(subscriptionJson);
                  if (subscription) {
                    var data = {"subscription": subscriptionJson};
                    $.post("/djtools/push_web_notification_subscription/",  data, function (data) {console.log(data); alert("Notificação ativada com sucesso.");});
                  } else {
                    alert("Problema ao ativar notificações.");
                    return;
                  }
                })
                .catch(function (err) {
                  alert("Problema ao tentar ativar notificações.");
                  console.log("Failed to subscribe the user: ", err);
                });
            } else {
              console.log("No registered service worker.");
            }
          })
          .catch(function (error) {
            alert("Erro");
            console.error("Service Worker Error", error);
          });
    } else {
    alert("Push messaging is not supported");
    }
}
