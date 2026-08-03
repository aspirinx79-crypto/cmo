/* ① 상품 서랍 — 매체별로 접고, 중요도 순으로 세우고, 판매중지는 잠근다. */
(function () {
  const WEIGHT_ORDER = { 상: 0, 중: 1, 하: 2 };
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

    list.querySelectorAll(".add-btn").forEach((btn) => {
      btn.addEventListener("click", () => addHandler(btn.dataset.id));
    });
  }

  function filter(term) {
    const q = (term || "").trim().toLowerCase();
    document.querySelectorAll(".product-row").forEach((row) => {
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
