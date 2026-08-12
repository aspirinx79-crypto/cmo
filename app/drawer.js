/* ① 상품 서랍 — 매체별로 접고, 중요도 순으로 세우고, 판매중지는 잠근다.

   맨 위에 「자주 쓰는 상품」을 따로 세운다. 카톡 12곳 기록에서 실제로
   몇 곳이 썼는지 세어 9곳 이상만 올렸다 — 그 아래는 6곳으로 뚝 떨어진다.
   서비스툴관리는 12곳 전부가 썼고 사실상 모든 견적에 들어가므로 맨 위다.

   매체별 목록에서 빼지 않고 위에 한 벌 더 둔다. 서랍은 매체로 찾는
   자리이기도 해서, 옮기면 "네이버에 있던 게 없어졌다"가 된다.

   마크업을 `.pin-row`/`.pin-add` 로 따로 쓴다. `.product-row`/`.add-btn`
   을 그대로 쓰면 같은 상품이 두 번 잡혀 `.add-btn[data-id=…]` 로 고르는
   자리가 전부 모호해진다. */
(function () {
  const WEIGHT_ORDER = { 상: 0, 중: 1, 하: 2 };

  // 카톡 12곳 기록에서 센 순서. 앞의 숫자는 그 상품을 쓴 매장 수다.
  const FREQUENT = [
    "네이버-서비스툴관리",              // 12곳 — 무조건 들어간다
    "네이버-SA",                        // 12곳
    "인스타-먹스타_PPL",                // 11곳
    "네이버-블로그_일반_체험단",         // 11곳
    "메타-타겟광고",                    // 11곳
    "네이버-카페_여론형성형_침투_바이럴", // 11곳
    "카카오-리뷰작업",                  // 11곳
    "네이버-플레이스_트래픽",            // 9곳
  ];

  let addHandler = () => {};
  let allProducts = [];

  const escapeHtml = window.Util.escapeHtml;

  function priceLabel(p) {
    if (p.가격유형 === "고정") return `${p.정가.toLocaleString()}원`;
    if (p.가격유형 === "예산배율") return `예산 ×${p.예산배율}`;
    if (p.가격유형 === "등급선택") return "등급별";
    return "협의";
  }

  function render(products) {
    allProducts = products;
    const byMedia = new Map();
    for (const p of products) {
      if (!byMedia.has(p.매체)) byMedia.set(p.매체, []);
      byMedia.get(p.매체).push(p);
    }

    const list = document.getElementById("drawer-list");
    list.innerHTML = "";

    // 자주 쓰는 상품. 없는 id 와 판매중지는 조용히 건너뛴다 — 서랍 맨
    // 위에 못 누르는 줄이 있으면 그게 더 헷갈린다.
    const pinned = FREQUENT
      .map((id) => products.find((p) => p.id === id))
      .filter((p) => p && !p.판매중지);

    if (pinned.length) {
      const group = document.createElement("div");
      group.className = "pin-group";
      group.innerHTML = `<div class="pin-head">자주 쓰는 상품</div>`;
      for (const p of pinned) {
        const row = document.createElement("div");
        row.className = "pin-row";
        row.dataset.id = p.id;
        // 매체를 함께 적는다. 「SA」는 네이버에도 구글에도 있고
        // 「리뷰작업」은 카카오에도 구글에도 있다 — 매체 없이는 어느
        // 쪽인지 알 수 없다. 매체별 목록 안에서는 위치로 알지만 여기선 아니다.
        row.innerHTML =
          `<span class="name">${escapeHtml(p.상품명)}</span>` +
          `<span class="media">${escapeHtml(p.매체)}</span>` +
          `<span class="price">${priceLabel(p)}</span>` +
          `<button class="pin-add" data-id="${escapeHtml(p.id)}">+</button>`;
        group.appendChild(row);
      }
      list.appendChild(group);
    }

    for (const [media, items] of byMedia) {
      items.sort((a, b) => {
        const w = (WEIGHT_ORDER[a.중요도] ?? 3) - (WEIGHT_ORDER[b.중요도] ?? 3);
        if (w !== 0) return w;
        return Number(a.판매중지) - Number(b.판매중지);
      });

      const group = document.createElement("details");
      group.className = "media-group";
      group.open = true;
      group.innerHTML = `<summary>${escapeHtml(media)} (${items.length})</summary>`;

      for (const p of items) {
        const row = document.createElement("div");
        row.className = "product-row" + (p.판매중지 ? " discontinued" : "");
        row.dataset.id = p.id;
        row.innerHTML =
          `<span class="name">${escapeHtml(p.상품명)}</span>` +
          `<span class="price">${priceLabel(p)}</span>` +
          `<button class="add-btn" data-id="${escapeHtml(p.id)}"${p.판매중지 ? " disabled" : ""}>+</button>`;
        group.appendChild(row);
      }
      list.appendChild(group);
    }

    list.querySelectorAll(".add-btn, .pin-add").forEach((btn) => {
      btn.addEventListener("click", () => addHandler(btn.dataset.id));
    });
  }

  function filter(term) {
    const q = (term || "").trim().toLowerCase();
    document.querySelectorAll(".product-row, .pin-row").forEach((row) => {
      const p = allProducts.find((x) => x.id === row.dataset.id);
      const hit = !q || `${p.상품명} ${p.매체}`.toLowerCase().includes(q);
      row.style.display = hit ? "" : "none";
    });
  }

  window.Drawer = {
    render,
    onAdd(cb) { addHandler = cb; },
  };

  document.addEventListener("DOMContentLoaded", async () => {
    document.getElementById("search").addEventListener("input", (e) => filter(e.target.value));
    try {
      render(await window.API.products());
    } catch (err) {
      const warnings = document.getElementById("warnings");
      if (warnings) warnings.textContent = `상품 목록을 불러오지 못했습니다: ${err.message}`;
    }
  });
})();
