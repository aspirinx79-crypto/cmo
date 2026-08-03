/* ② 구성판 — 담긴 항목을 카드로 쌓고 금액을 계산한다.
   금액 계산은 서버(lib/pricing.py)가 정본이다. 화면은 표시만 한다.
   같은 규칙을 두 곳에 적으면 언젠가 두 답이 갈린다. */
(function () {
  const state = new Map();   // 상품id → item
  let products = [];
  let productsLoaded = false;
  let pendingAdds = [];       // products 로딩이 끝나기 전에 눌린 담기 클릭
  let changeHandler = () => {};

  const won = (n) => `${Number(n || 0).toLocaleString()}원`;
  const escapeHtml = window.Util.escapeHtml;

  function warn(message) {
    const el = document.getElementById("warnings");
    if (el) el.textContent = message;
  }

  function product(id) {
    return products.find((p) => p.id === id);
  }

  function itemsArray() {
    return [...state.values()];
  }

  function cardHTML(p, item) {
    const notice = p.고지사항
      ? `<div class="notice">⚠ ${escapeHtml(p.고지사항)}</div>` : "";

    let control = "";
    if (p.가격유형 === "고정") {
      control = `<label>수량 <input class="qty-input" type="number" min="0"
        value="${item.수량 ?? p.최소수량 ?? 1}"> ${escapeHtml(p.단위 || "건")}</label>`;
    } else if (p.가격유형 === "예산배율") {
      control = `<label>월 집행예산 <input class="budget-input" type="number"
        step="100000" value="${item.예산 ?? 0}">원 (정가 ×${p.예산배율})</label>`;
    } else if (p.가격유형 === "등급선택") {
      const options = (p.등급 || [])
        .map((g) => {
          const name = escapeHtml(g.이름);
          return `<option value="${name}"${item.등급 === g.이름 ? " selected" : ""}>${name}</option>`;
        })
        .join("");
      control = `<label>등급 <select class="grade-select">${options}</select></label>
        <label>수량 <input class="qty-input" type="number" min="1" value="${item.수량 ?? 1}"></label>`;
    } else {
      control = `<label>정가 <input class="manual-list-price" type="number"
          step="10000" value="${item.정가 ?? 0}"></label>
        <label>실비 <input class="manual-cost" type="number"
          step="10000" value="${item.실비 ?? 0}"></label>`;
    }

    return `
      <div class="card-head">
        <strong>${escapeHtml(p.상품명)}</strong>
        <span class="media">${escapeHtml(p.매체)}</span>
        <button class="remove-btn" type="button">×</button>
      </div>
      <div class="card-body">${control}</div>
      <div class="line-total">—</div>
      ${notice}`;
  }

  function bind(card, id) {
    const item = state.get(id);

    const qty = card.querySelector(".qty-input");
    if (qty) qty.addEventListener("change", () => {
      item.수량 = Number(qty.value); refresh();
    });

    const budget = card.querySelector(".budget-input");
    if (budget) budget.addEventListener("change", () => {
      item.예산 = Number(budget.value); refresh();
    });

    const grade = card.querySelector(".grade-select");
    if (grade) grade.addEventListener("change", () => {
      item.등급 = grade.value; refresh();
    });

    const listPrice = card.querySelector(".manual-list-price");
    if (listPrice) listPrice.addEventListener("change", () => {
      item.정가 = Number(listPrice.value); refresh();
    });

    const cost = card.querySelector(".manual-cost");
    if (cost) cost.addEventListener("change", () => {
      item.실비 = Number(cost.value); refresh();
    });

    card.querySelector(".remove-btn").addEventListener("click", () => {
      state.delete(id); draw(); refresh();
    });
  }

  function draw() {
    const list = document.getElementById("board-list");
    list.innerHTML = "";
    for (const [id, item] of state) {
      const p = product(id);
      const card = document.createElement("article");
      card.className = "board-card";
      card.dataset.id = id;
      card.innerHTML = cardHTML(p, item);
      list.appendChild(card);
      bind(card, id);
    }
  }

  async function refresh() {
    const 계약가 = Number(document.getElementById("contract-price").value || 0);
    const items = itemsArray();

    let result;
    try {
      result = await window.API.summary(items, 계약가);
    } catch (err) {
      // 알 수 없는 등급 이름 등으로 서버가 400 을 내면 여기로 온다.
      // 조용히 멈추면 화면 숫자가 안 바뀌는데 이유를 알 수 없다.
      warn(`합계를 계산하지 못했습니다: ${err.message}`);
      return;
    }

    // 줄별 금액도 같은 응답에 들어 있다. 항목마다 다시 부르지 않는다.
    for (const line of result.줄별) {
      const card = document.querySelector(`.board-card[data-id="${CSS.escape(line.상품id)}"]`);
      if (card) card.querySelector(".line-total").textContent = won(line.정가);
    }

    warn(result.경고.join(" · "));
    changeHandler(result, items);
  }

  function addNow(id) {
    if (state.has(id)) return;
    const p = product(id);
    if (!p || p.판매중지) return;
    state.set(id, {
      상품id: id,
      수량: p.가격유형 === "고정" ? (p.최소수량 || 1) : 1,
      예산: 0,
      등급: (p.등급 && p.등급[0] && p.등급[0].이름) || null,
      정가: 0,
      실비: 0,
    });
    draw();
    refresh();
  }

  function add(id) {
    // 상품 목록이 아직 안 실렸으면(드로어보다 늦게 끝나는 fetch) 클릭을 버리지
    // 않고 쌓아 둔다 — 미팅 자리에서 담기를 눌렀는데 아무 일도 안 일어나는 건
    // 안내도 없이 넘길 수 있는 결함이 아니다.
    if (!productsLoaded) { pendingAdds.push(id); return; }
    addNow(id);
  }

  function load(items) {
    state.clear();
    for (const item of items) state.set(item.상품id, { ...item });
    draw();
    refresh();
  }

  window.Board = {
    items: itemsArray,
    add, load,
    clear() { state.clear(); draw(); refresh(); },
    onChange(cb) { changeHandler = cb; },
  };

  document.addEventListener("DOMContentLoaded", async () => {
    // 이 두 줄은 아래 await 앞에 있어야 한다. drawer.js 도 자기 상품목록을
    // 독립적으로 fetch 하는데, 그게 먼저 끝나 .add-btn 이 그려지고 나면
    // 클릭이 곧장 addHandler 로 간다. onAdd 등록이 fetch 완료 뒤로 밀리면
    // 그 사이의 클릭은 기본 no-op 으로 들어가 소리 없이 사라진다.
    window.Drawer.onAdd(add);
    document.getElementById("contract-price").addEventListener("change", refresh);

    try {
      products = await window.API.products();
    } catch (err) {
      warn(`상품 목록을 불러오지 못했습니다: ${err.message}`);
      return;
    }

    productsLoaded = true;
    const queued = pendingAdds;
    pendingAdds = [];
    queued.forEach(addNow);
  });
})();
