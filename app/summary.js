/* ③ 요약 — 고객에게 보여줄 숫자와 내부 숫자를 갈라서 보여준다.
   가리기 버튼은 사장님이 화면 쪽으로 다가올 때 누른다. */
(function () {
  const won = (n) => `${Number(n || 0).toLocaleString()}원`;
  let currentSummary = null;
  let currentItems = [];

  function paint(result, items) {
    currentSummary = result;
    currentItems = items;

    const 계약가 = Number(document.getElementById("contract-price").value || 0);
    document.getElementById("list-total").textContent = won(result.정가합);
    document.getElementById("contract-total").textContent = won(계약가);
    document.getElementById("cost-total").textContent = won(result.실비합);
    document.getElementById("margin").textContent = won(result.마진);

    document.getElementById("margin-rate").textContent =
      result.마진율 === null ? "—" : `${(result.마진율 * 100).toFixed(1)}%`;

    document.getElementById("multiplier").textContent =
      result.혜택배율 === null
        ? "—"
        : `${result.혜택배율.toFixed(1)}배 — ${won(result.정가합)} 상당을 ${won(계약가)}에`;
  }

  function currentPlan() {
    return {
      월: document.getElementById("month").value,
      계약가: Number(document.getElementById("contract-price").value || 0),
      진단메모: "",
      항목: currentItems,
      작성일: new Date().toISOString().slice(0, 10),
    };
  }

  function slug() {
    return document.getElementById("client-select").value;
  }

  async function save() {
    if (!slug()) { alert("고객사를 먼저 선택하십시오."); return; }
    const plan = currentPlan();
    try {
      await window.API.savePlan(slug(), plan.월, plan, false);
      alert(`${plan.월} 기획안을 저장했습니다.`);
    } catch (err) {
      if (err.status === 409) {
        if (confirm(`${plan.월} 기획안이 이미 있습니다. 덮어쓸까요?\n지난 기록이 사라집니다.`)) {
          try {
            await window.API.savePlan(slug(), plan.월, plan, true);
            alert("덮어썼습니다.");
          } catch (err2) {
            alert(`저장 실패: ${err2.message}`);
          }
        }
        return;
      }
      alert(`저장 실패: ${err.message}`);
    }
  }

  async function copyNext() {
    if (!slug()) { alert("고객사를 먼저 선택하십시오."); return; }
    const month = document.getElementById("month").value;
    const [y, m] = month.split("-").map(Number);
    const next = m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`;
    try {
      const copied = await window.API.copyPlan(slug(), month, next);
      document.getElementById("month").value = next;
      document.getElementById("contract-price").value = copied.계약가;
      window.Board.load(copied.항목);
      alert(`${next} 로 복제했습니다.`);
    } catch (err) {
      alert(err.status === 409 ? `${next} 기획안이 이미 있습니다.` : `복제 실패: ${err.message}`);
    }
  }

  async function loadClients() {
    const select = document.getElementById("client-select");
    let clients;
    try {
      clients = await window.API.clients();
    } catch (err) {
      const el = document.getElementById("warnings");
      if (el) el.textContent = `고객사 목록을 불러오지 못했습니다: ${err.message}`;
      return;
    }
    for (const c of clients) {
      const option = document.createElement("option");
      option.value = c.slug;
      option.textContent = c.이름;
      select.appendChild(option);
    }
  }

  window.Summary = { currentPlan };

  document.addEventListener("DOMContentLoaded", async () => {
    window.Board.onChange(paint);

    document.getElementById("hide-internal").addEventListener("click", () => {
      const box = document.getElementById("internal");
      const hidden = box.classList.toggle("hidden");
      // #internal(오른쪽 단)만 가리는 걸로는 부족하다 — 직접입력 상품의
      // 실비는 구성판(가운데 단)의 .manual-cost 입력칸에 산다. body 에도
      // 같은 상태를 반영해 app.css 가 두 곳을 한 번에 가리게 한다.
      document.body.classList.toggle("hide-internal", hidden);
      document.getElementById("hide-internal").textContent =
        hidden ? "보기" : "가리기";
    });

    document.getElementById("save-plan").addEventListener("click", save);
    document.getElementById("copy-next").addEventListener("click", copyNext);

    document.getElementById("client-select").addEventListener("change", async (e) => {
      if (!e.target.value) return;
      try {
        const months = await window.API.planMonths(e.target.value);
        if (!months.length) return;
        const plan = await window.API.plan(e.target.value, months[0]);
        document.getElementById("month").value = plan.월;
        document.getElementById("contract-price").value = plan.계약가;
        window.Board.load(plan.항목);
      } catch (err) {
        const el = document.getElementById("warnings");
        if (el) el.textContent = `기획안을 불러오지 못했습니다: ${err.message}`;
      }
    });

    await loadClients();
  });
})();
