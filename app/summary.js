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
      if (hide) {
        label.setAttribute("hidden", "");
        // hidden 속성만으로는 부족하다 — 매장 준비 패널의 라벨은
        // app.css 의 `#metrics label { display: grid }` 가 ID 선택자라,
        // [hidden] 이 거는 UA 기본 display:none 을 이겨 버린다(author
        // 규칙은 특정도와 무관하게 UA 규칙을 항상 이긴다). 인라인
        // !important 로 직접 꺼야 이 자리에서도 확실히 가려진다.
        label.style.setProperty("display", "none", "important");
      } else {
        label.removeAttribute("hidden");
        label.style.removeProperty("display");
      }
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

  // 저장 계약 — 저장 버튼과 제안서 만들기가 같이 쓴다.
  //
  // force=false 로 먼저 시도한다. 서버가 409 를 내면(그 달 기획안이 이미
  // 있다) 사용자에게 묻고, 승낙했을 때만 force=true 로 덮어쓴다. 묻지 않고
  // 덮어쓰면 지난달에 확정해 둔 기획안이 소리 없이 사라진다.
  //
  // 반환: {saved: true, overwritten: bool} 또는 {saved: false} (사용자가 거절).
  // 저장 자체가 실패하면 예외를 그대로 던진다 — 부르는 쪽이 문맥에 맞는
  // 메시지를 붙인다.
  async function savePlanAskingToOverwrite(plan) {
    try {
      await window.API.savePlan(slug(), plan.월, plan, false);
      return { saved: true, overwritten: false };
    } catch (err) {
      if (err.status !== 409) throw err;
      if (!confirm(`${plan.월} 기획안이 이미 있습니다. 덮어쓸까요?\n지난 기록이 사라집니다.`)) {
        return { saved: false, overwritten: false };
      }
      await window.API.savePlan(slug(), plan.월, plan, true);
      return { saved: true, overwritten: true };
    }
  }

  async function save() {
    if (!slug()) { alert("고객사를 먼저 선택하십시오."); return; }
    const plan = currentPlan();
    try {
      const r = await savePlanAskingToOverwrite(plan);
      if (!r.saved) return;
      alert(r.overwritten ? "덮어썼습니다." : `${plan.월} 기획안을 저장했습니다.`);
    } catch (err) {
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

  async function loadClients(selectSlug) {
    const select = document.getElementById("client-select");
    let clients;
    try {
      clients = await window.API.clients();
    } catch (err) {
      const el = document.getElementById("warnings");
      if (el) el.textContent = `고객사 목록을 불러오지 못했습니다: ${err.message}`;
      return;
    }
    // 매장을 새로 등록하면 이 함수가 다시 불린다. 비우지 않으면 같은
    // 매장이 두 번 쌓인다.
    const keep = select.value;
    select.innerHTML = '<option value="">고객사 선택…</option>';
    for (const c of clients) {
      const option = document.createElement("option");
      option.value = c.slug;
      option.textContent = c.이름;
      select.appendChild(option);
    }
    select.value = selectSlug || keep || "";
    // select.value 대입은 change 이벤트를 내지 않는다. 드롭다운만 새 매장을
    // 가리키고 구성판은 앞 매장인 상태를 직접 막는다.
    if (selectSlug) await loadClientPlan(selectSlug);
  }

  // index.html #contract-price 의 초기 value 와 맞춘다. 기획안이 없는
  // 매장으로 바꿨을 때(아래) 계약가를 이 값으로 되돌린다 — 0원으로
  // 비우면 「N배」 줄이 계약가 0을 놓고 계산되어 다른 방식으로 왜곡되고,
  // 빈 값도 Number("") 가 0 으로 읽혀 결국 같다. 새로 이 도구를 연 것과
  // 같은 화면으로 되돌리는 편이 사장님 앞에서 자연스럽다.
  const DEFAULT_CONTRACT_PRICE = "1000000";

  // 고객사를 바꾸면 그 매장의 최신 기획안을 올린다.
  // 기획안이 없는 매장(방금 등록한 신규)이면 구성판을 비운다 — 앞 매장 항목이
  // 남은 채로 저장하면 A 매장 기획안이 B 매장 밑에 저장된다.
  async function loadClientPlan(slug) {
    if (!slug) return;
    try {
      const months = await window.API.planMonths(slug);
      if (!months.length) {
        // 계약가도 같이 초기화한다 — 안 하면 앞 매장 계약가가 남아 「N배」
        // 줄을 잘못 계산하고, 그 상태로 저장하면 이 매장의 새 기획안에
        // 앞 매장 계약가가 그대로 들어간다. #month 는 사용자가 고른
        // 값이라 그대로 둔다.
        document.getElementById("contract-price").value = DEFAULT_CONTRACT_PRICE;
        window.Board.load([]);
        return;
      }
      const plan = await window.API.plan(slug, months[0]);
      document.getElementById("month").value = plan.월;
      document.getElementById("contract-price").value = plan.계약가;
      window.Board.load(plan.항목);
    } catch (err) {
      const el = document.getElementById("warnings");
      if (el) el.textContent = `기획안을 불러오지 못했습니다: ${err.message}`;
      // 읽기 실패는 "기획안 없음"과 같은 위험을 안는다 — 구성판에 앞
      // 매장 항목이 남은 채로 저장을 누르면 그 매장 기획안이 지금 고른
      // 매장 폴더에 저장된다. 비워서 막는다. (I-3)
      document.getElementById("contract-price").value = DEFAULT_CONTRACT_PRICE;
      window.Board.load([]);
    }
  }

  // 가리기 토글의 유일한 구현. #hide-internal(요약 칸)과
  // #panel-hide-internal(매장 준비 패널) 두 버튼이 이 함수 하나를 부른다.
  // 규칙이 두 벌이 되면 그게 사고다 — 한쪽만 누르고 다른 쪽은 안 가려지는
  // 상태가 생긴다. 두 버튼 모두 같은 body.hide-internal 상태를 공유하므로
  // 글자("가리기"/"보기")도 항상 같이 바뀐다.
  function toggleConcealment() {
    const box = document.getElementById("internal");
    const hidden = box.classList.toggle("hidden");
    // #internal(오른쪽 단)만 가리는 걸로는 부족하다 — 직접입력 상품의
    // 실비는 구성판(가운데 단)의 .manual-cost 입력칸에 산다. body 에도
    // 같은 상태를 반영해 app.css 가 두 곳을 한 번에 가리게 한다.
    document.body.classList.toggle("hide-internal", hidden);
    // 토글 자체는 구성판을 다시 그리지 않으므로(카드 개수·값이 안
    // 바뀐다) paint() 가 저절로 안 불린다 — 여기서 직접 적용한다.
    applyBoardConcealment();
    const label = hidden ? "보기" : "가리기";
    document.getElementById("hide-internal").textContent = label;
    const panelBtn = document.getElementById("panel-hide-internal");
    if (panelBtn) panelBtn.textContent = label;
    return hidden;
  }

  window.Summary = {
    currentPlan,
    reloadClients: loadClients,
    applyConcealment: applyBoardConcealment,
    toggleConcealment,
  };

  /* 프리셋 드롭다운. 실집행에서 반복된 조합을 한 번에 올린다.
     불러온 뒤에는 그냥 구성판의 항목이라, 빼고 더하는 데 제약이 없다.

     프리셋을 못 읽어도 도구는 열려야 한다. 여기서 예외가 새면
     DOMContentLoaded 가 통째로 죽어서 고객사 목록까지 안 뜬다 —
     미팅 자리에서 도구가 빈 화면으로 열리는 게 최악이다. */
  async function loadPresets() {
    const select = document.getElementById("preset-select");
    if (!select) return;
    let presets;
    try {
      presets = await window.API.presets();
    } catch (err) {
      const el = document.getElementById("warnings");
      if (el) el.textContent = `프리셋을 불러오지 못했습니다: ${err.message}`;
      return;
    }
    presets.forEach((p, i) => {
      const option = document.createElement("option");
      option.value = String(i);
      // 출처를 같이 보여준다. "어느 매장에서 실제로 돌린 조합인지" 가
      // 사장님 앞에서 근거가 된다. 출처 없는 프리셋은 시드가 막는다.
      option.textContent = `${p.이름} (${p.출처})`;
      select.appendChild(option);
    });
    select.addEventListener("change", (e) => {
      if (e.target.value === "") return;
      window.Board.load(presets[Number(e.target.value)].항목);
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    window.Board.onChange(paint);

    document.getElementById("hide-internal").addEventListener("click", toggleConcealment);

    document.getElementById("save-plan").addEventListener("click", save);
    document.getElementById("copy-next").addEventListener("click", copyNext);

    document.getElementById("make-proposal").addEventListener("click", async () => {
      if (!slug()) { alert("고객사를 먼저 선택하십시오."); return; }
      const plan = currentPlan();
      try {
        // 제안서는 저장된 기획안을 읽어서 만든다. 그래서 먼저 저장해야
        // 하는데, 그 저장도 저장 버튼과 같은 계약을 따른다. 사용자가
        // 덮어쓰기를 거절하면 PDF 도 만들지 않는다 — 거절했는데도 제안서가
        // 나오면 그 제안서는 화면에 있는 구성이 아니라 예전 기획안으로
        // 만들어진 물건이라, 들고 나간 사람이 속는다.
        const r = await savePlanAskingToOverwrite(plan);
        if (!r.saved) return;
        const made = await window.API.proposal(slug(), plan.월);
        alert(`제안서를 만들었습니다.\n${made.경로}`);
      } catch (err) {
        alert(`제안서 생성 실패: ${err.message}`);
      }
    });

    document.getElementById("client-select").addEventListener("change", (e) => {
      loadClientPlan(e.target.value);
    });

    await loadPresets();
    await loadClients();
  });
})();
