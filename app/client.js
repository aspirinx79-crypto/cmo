/* 매장 준비 패널 — 미팅 전 사무실에서 하는 일이 전부 여기 모인다.
   등록 · 편집 · 플레이스 수집 · 순위와 오픈업 수동 입력.

   미팅 화면(서랍·구성판·요약)은 이 파일이 건드리지 않는다. 뒤에 그대로
   살아 있고 패널을 닫으면 돌아온다. */
(function () {
  let keywords = [];
  let editingSlug = null;   // null 이면 신규 등록

  const el = (id) => document.getElementById(id);
  const text = (id) => el(id).value.trim();

  // 빈 숫자칸은 0 이 아니라 null 이다. 0평은 제안서에 찍히고 null 은
  // 그 줄이 아예 안 그려진다. 사장님은 자기 가게 평수를 안다.
  function num(id) {
    const v = el(id).value.trim();
    return v === "" ? null : Number(v);
  }

  function say(id, message, ok) {
    const box = el(id);
    box.textContent = message;
    box.classList.toggle("ok", Boolean(ok));
  }

  function paintKeywords() {
    const list = el("keyword-list");
    list.innerHTML = "";
    keywords.forEach((kw, i) => {
      const li = document.createElement("li");
      const span = document.createElement("span");
      span.textContent = kw;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "빼기";
      btn.addEventListener("click", () => {
        keywords.splice(i, 1);
        paintKeywords();
        paintRankRows();
      });
      li.append(span, btn);
      list.appendChild(li);
    });
  }

  // 순위는 키워드 없이 성립하지 않는다. 입력줄이 키워드 목록을 따라간다.
  function paintRankRows() {
    const box = el("rank-rows");
    box.innerHTML = "";
    keywords.forEach((kw) => {
      const label = document.createElement("label");
      label.className = "rank-row";
      label.dataset.keyword = kw;
      const name = document.createElement("span");
      name.textContent = kw;
      const input = document.createElement("input");
      input.type = "number";
      input.min = "1";
      input.className = "rank-input";
      label.append(name, input);
      box.appendChild(label);
    });
  }

  function fill(client) {
    el("f-name").value = client.이름 || "";
    el("f-place-url").value = client.플레이스URL || "";
    el("f-category").value = client.업종 || "";
    el("f-area").value = client.지역 || "";
    el("f-size").value = client.평수 ?? "";
    el("f-ticket").value = client.객단가 ?? "";
    el("f-start").value = client.계약시작 || el("month").value;
    el("f-status").value = client.상태 || "진행중";
    el("f-memo").value = client.메모 || "";
    keywords = [...(client.추적키워드 || [])];
    paintKeywords();
    paintRankRows();
    paintLastSnapshot(client);

    // 지표 칸은 매장마다 새로 입력한다. 앞 매장 값이 남아 있으면
    // saveMetrics() 가 그걸 다음 매장에 그대로 얹는다 — #f-revenue 는
    // .manual-cost 라 가리기가 켜져 있으면 안 보이는 채로 남의 매장에
    // 저장된다.
    el("f-market-rank").value = "";
    el("f-revenue").value = "";
    el("f-keyword").value = "";
    el("f-fetch-place").checked = true;
  }

  function paintLastSnapshot(client) {
    const list = client.스냅샷 || [];
    if (!list.length) { el("last-snapshot").textContent = "—"; return; }
    const s = list[list.length - 1];
    const p = s.플레이스 || {};
    const n = (v) => (v === null || v === undefined ? "—" : v);
    el("last-snapshot").textContent =
      `마지막 ${s.수집시각} · 방문자리뷰 ${n(p.방문자리뷰)}` +
      ` · 블로그리뷰 ${n(p.블로그리뷰)} · 저장수 ${n(p.저장수)}`;
  }

  function formData() {
    return {
      이름: text("f-name"),
      플레이스URL: text("f-place-url"),
      업종: text("f-category"),
      지역: text("f-area"),
      평수: num("f-size"),
      객단가: num("f-ticket"),
      계약시작: text("f-start"),
      상태: el("f-status").value,
      추적키워드: [...keywords],
      메모: text("f-memo"),
    };
  }

  function lock(disabled) {
    if (disabled) el("metrics").setAttribute("disabled", "");
    else el("metrics").removeAttribute("disabled");
  }

  async function open(slug) {
    editingSlug = slug || null;
    el("panel-title").textContent = slug ? "매장 정보" : "새 매장";
    say("client-msg", "");
    say("metrics-msg", "");
    // 수집은 서버가 저장된 매장을 읽어야 돈다. 신규는 저장 전까지 잠근다.
    lock(!slug);

    // 먼저 비우고 연다. 서버 응답을 기다리는 사이 앞 매장 값이 보이면
    // 미팅 자리에서 B 사장님에게 A 매장 정보를 보이는 셈이 된다.
    fill({});
    el("client-panel").removeAttribute("hidden");
    // 가리기가 켜진 상태로 열면 월매출칸이 그대로 보인다.
    // 규칙이 화면마다 다르면 그게 사고가 된다.
    window.Summary.applyConcealment();

    if (slug) {
      try {
        fill(await window.API.client(slug));
      } catch (err) {
        say("client-msg", `매장 정보를 불러오지 못했습니다: ${err.message}`);
        // 폼은 이미 fill({}) 로 비워진 채다. 이름을 다시 쳐서 저장을
        // 누르면 업종·지역·평수·객단가·추적키워드가 전부 빈 값으로
        // 실매장을 덮어쓴다. 쓰는 길만 끊는다 — 저장 버튼을 끄면
        // Enter 로 인한 암묵적 제출도 같이 막힌다(제출 버튼이 비활성이면
        // 브라우저가 폼을 보내지 않는다). 칸 자체는 그대로 두어 상무님이
        // 무슨 화면인지 볼 수 있게 한다.
        // 패널은 열어 두고 메시지는 보이게 둔다 — I-5 에서 얻은 것이다.
        lock(true);
        el("save-client").setAttribute("disabled", "");
        return;
      }
      // fill() 이 #f-revenue 를 다시 그리므로 가리기를 재적용한다.
      window.Summary.applyConcealment();
    }
    // 이전에 열었을 때 실패해 잠갔을 수 있다(위 catch). 이번엔 성공했으니
    // 다시 눌러 저장할 수 있어야 한다 — 여기서 안 풀면 다음에 패널을 열
    // 때도 잠긴 채로 남는다.
    el("save-client").removeAttribute("disabled");
  }

  function close() {
    el("client-panel").setAttribute("hidden", "");
  }

  async function saveClient(event) {
    event.preventDefault();
    const data = formData();
    if (!data.이름) { say("client-msg", "이름을 입력하십시오."); return; }

    try {
      if (editingSlug) {
        // 스냅샷은 폼에 없다. 읽어서 그대로 얹지 않으면 수집 이력이 날아간다.
        // 메모는 이제 폼(#f-memo)의 몫이다 — data.메모 를 그대로 쓴다.
        // before.메모 로 덮으면 방금 고친 메모가 저장 직후 원래대로
        // 되돌아간다.
        const before = await window.API.client(editingSlug);
        await window.API.saveClient(editingSlug, {
          ...data, slug: editingSlug, 스냅샷: before.스냅샷 || [],
        });
      } else {
        const made = await window.API.createClient(data);
        editingSlug = made.slug;
      }
    } catch (err) {
      say("client-msg", err.message);
      return;
    }

    lock(false);
    await window.Summary.reloadClients(editingSlug);
    say("client-msg", `${data.이름} 을(를) 저장했습니다.`, true);
  }

  async function saveMetrics() {
    if (!editingSlug) return;
    const ranks = [...document.querySelectorAll("#rank-rows .rank-row")]
      .map((row) => ({
        키워드: row.dataset.keyword,
        순위: row.querySelector(".rank-input").value.trim() === ""
          ? null : Number(row.querySelector(".rank-input").value),
      }))
      .filter((r) => r.순위 !== null);

    const 상권순위 = text("f-market-rank");
    const 월매출 = num("f-revenue");
    const revenue = (상권순위 || 월매출 !== null)
      ? { 월매출, 상권순위, 출처: "오픈업", 입력방식: "수동" }
      : null;

    // 저장 중에는 이 칸을 비워 둔다. 화면을 기다리는 쪽이 .ok 와 :not(.ok)
    // 로 이 칸의 모든 상태를 나눠 갖고 있어서, 중간 문구를 넣으면 어느
    // 쪽이든 저장이 끝나기 전에 걸린다. 진행 중임은 버튼을 잠가 알린다.
    say("metrics-msg", "");
    const button = el("save-metrics");
    button.disabled = true;
    try {
      await window.API.collect({
        slug: editingSlug,
        순위: ranks,
        예상매출: revenue,
        플레이스수집: el("f-fetch-place").checked,
      });
    } catch (err) {
      // 서버 메시지에 탈출구가 적혀 있다. 그대로 보여준다.
      say("metrics-msg", err.message);
      return;
    } finally {
      button.disabled = false;
    }
    try {
      paintLastSnapshot(await window.API.client(editingSlug));
      say("metrics-msg", "지표를 저장했습니다.", true);
    } catch (err) {
      // 저장 자체는 이미 성공했다(위 collect() 가 던지지 않고 통과했다).
      // 이 읽기는 화면의 "마지막 수집" 줄을 새로고침하는 용도일 뿐이라,
      // 실패해도 성공 메시지는 그대로 띄운다 — 안 그러면 실제로는 저장된
      // 지표를 상무님이 못 본 걸로 알고 다시 눌러 스냅샷이 중복 쌓인다.
      say("metrics-msg", "지표를 저장했습니다. (최근 수집 표시는 갱신하지 못했습니다.)", true);
    }
  }

  window.ClientPanel = { open };

  document.addEventListener("DOMContentLoaded", () => {
    el("new-client").addEventListener("click", () => open(null));
    el("edit-client").addEventListener("click", () => {
      const slug = el("client-select").value;
      if (!slug) { alert("고객사를 먼저 선택하십시오."); return; }
      open(slug);
    });
    el("panel-close").addEventListener("click", close);
    el("client-form").addEventListener("submit", saveClient);
    el("save-metrics").addEventListener("click", saveMetrics);
    // 패널이 열려 있으면 백드롭이 클릭을 막아 #hide-internal(요약 칸)에
    // 손이 안 닿는다(I-5) — 패널 안에도 같은 버튼을 두고 같은 함수를
    // 부른다. 새로 구현하지 않는다: 규칙이 두 벌이 되는 게 사고다.
    el("panel-hide-internal").addEventListener("click", () => {
      window.Summary.toggleConcealment();
    });

    el("add-keyword").addEventListener("click", () => {
      const kw = text("f-keyword");
      if (!kw || keywords.includes(kw)) return;
      keywords.push(kw);
      el("f-keyword").value = "";
      paintKeywords();
      paintRankRows();
    });
  });
})();
