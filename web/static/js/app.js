// JavaScript lokal untuk menghindari script inline (CSP: script-src 'self').
document.addEventListener("click", function (event) {
  var target = event.target;

  // Cetak struk
  if (target.closest("[data-print]")) {
    window.print();
    return;
  }

  // Chip nominal cepat: <button data-fill="50000" data-target="amount">
  var chip = target.closest("[data-fill]");
  if (chip) {
    var input = document.getElementById(chip.getAttribute("data-target"));
    if (input) {
      input.value = chip.getAttribute("data-fill");
      input.focus();
    }
    return;
  }

  // Sembunyikan / tampilkan saldo: <button data-toggle-balance="#bal">
  var eye = target.closest("[data-toggle-balance]");
  if (eye) {
    var el = document.querySelector(eye.getAttribute("data-toggle-balance"));
    if (el) {
      if (el.getAttribute("data-hidden") === "1") {
        el.textContent = el.getAttribute("data-real");
        el.setAttribute("data-hidden", "0");
      } else {
        el.setAttribute("data-real", el.textContent);
        el.textContent = "Rp \u2022\u2022\u2022\u2022\u2022\u2022";
        el.setAttribute("data-hidden", "1");
      }
    }
  }
});
