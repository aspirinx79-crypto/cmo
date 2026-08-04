/* ③ 요약 — 고객에게 보여줄 숫자와 내부 숫자를 갈라서 보여준다.
   가리기 버튼은 사장님이 화면 쪽으로 다가올 때 누른다. */
(function () {
  const won = (n) => `${Number(n || 0).toLocaleString()}원`;
  let currentSummary = null;
  let currentItems = [];

  // 가리기의 유일한 수단을 app.css 의 `:has()` 규칙 하나에 걸지 않는다.
  // `:has()` 를 모르는 브라우저는 그 규칙 자체를 파싱 단계에서 통째로
  // 버린다 — 조용히, 콘솔 오류도 없이. 결과는 "미팅 중 사장님에게 원가가
  // 그대로 보인다" 다. 확률이 낮아도 실패는 닫히는 쪽이어야 하므로, JS 로
  // `hidden` 속성을 직접 세운다(`hidden` 은 UA 기본 스타일시트가
  // `display: none` 을 주므로 CSS 지원 여부와 무관하게 어느 브라우저에서나
  // 먹는다). CSS 규칙은 그대로 둔다 — 렌더 즉시 걸려 깜빡임이 없고, 이
  // JS 는 CSS 가 안 먹을 때의 안전망이다.
  //
  // 구성판이 다시 그려질 때마다(항목 추가/삭제/수량 변경 등) board.js 가
  // 카드 마크업을 통째로 새로 만들어 이 속성이 날아간다. board.js 는 카드를
  // 다시 그린 뒤 반드시 refresh() → onChange(paint) 로 이어지므로, paint()
  // 를 재적용 지점으로 쓴다.
  function applyBoardConcealment() {
    const hide = document.body.classList.contains("hide-internal");
    document.querySelectorAll(".manual-cost").forEach((input) => {
      const label = input.closest("label");
      if (!label) return;
      if (hide) label.setAttribute("hidden", "");
      else label.removeAttribute("hidden");
    });
  }

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

    applyBoardConcealment();
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
      // 토글 자체는 구성판을 다시 그리지 않으므로(카드 개수·값이 안
      // 바뀐다) paint() 가 저절로 안 불린다 — 여기서 직접 적용한다.
      applyBoardConcealment();
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
