/* 공용 유틸 — 여러 화면 스크립트가 같이 쓴다. index.html 에서 다른 앱 스크립트보다
   먼저 실려야 한다. 여기 없는 동작을 추가할 땐 정말 여러 화면이 같이 쓰는지부터 물어라. */
(function () {
  // 상품 데이터는 상무님이 손으로 편집하는 시트에서 온다 — 괄호·슬래시·따옴표가
  // 이미 많다. innerHTML 에 꽂기 전에는 반드시 이 함수를 거친다.
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  window.Util = { escapeHtml };
})();
