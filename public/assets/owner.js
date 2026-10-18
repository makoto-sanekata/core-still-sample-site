// ［送る］を押すと「送信しました（見本）」と出すだけ。実際には何も送らない。
document.querySelectorAll('[data-send]').forEach(function (button) {
  button.addEventListener('click', function () {
    var message = document.getElementById(button.getAttribute('data-send'));
    if (message) { message.hidden = false; }
    button.disabled = true;
  });
});
