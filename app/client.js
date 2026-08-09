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
    keywords = [...(client.추적키워드 || [])];
    paintKeywords();
    paintRankRows();
    paintLastSnapshot(client);
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
      메모: "",
    };
  }

  function lock(disabled) {
    const box = el("metrics");
    if (disabled) {
      box.setAttribute("disabled", "");
      // <fieldset disabled> real 로 descendant 입력을 막지만, Playwright 의
      // is_disabled() 는 FIELDSET 을 네이티브 비활성 태그 목록(BUTTON,
      // INPUT, SELECT, TEXTAREA, OPTION, OPTGROUP)에 넣지 않는다 — fieldset
      // 자기 자신을 물으면 disabled 속성이 있어도 false 를 돌려준다.
      // aria-disabled 를 같이 세워 그 갭을 메운다.
      box.setAttribute("aria-disabled", "true");
    } else {
      box.removeAttribute("disabled");
      box.setAttribute("aria-disabled", "false");
    }
  }

  async function open(slug) {
    editingSlug = slug || null;
    el("panel-title").textContent = slug ? "매장 정보" : "새 매장";
    say("client-msg", "");
    say("metrics-msg", "");
    // 수집은 서버가 저장된 매장을 읽어야 돈다. 신규는 저장 전까지 잠근다.
    lock(!slug);

    if (slug) {
      try {
        fill(await window.API.client(slug));
      } catch (err) {
        say("client-msg", `매장 정보를 불러오지 못했습니다: ${err.message}`);
        return;
      }
    } else {
      fill({});
    }

    el("client-panel").removeAttribute("hidden");
    // 가리기가 켜진 상태로 패널을 열면 월매출칸이 그대로 보인다.
    // 규칙이 화면마다 다르면 그게 사고가 된다.
    window.Summary.applyConcealment();
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
        const before = await window.API.client(editingSlug);
        await window.API.saveClient(editingSlug, {
          ...data, slug: editingSlug, 스냅샷: before.스냅샷 || [],
          메모: before.메모 || "",
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

    say("metrics-msg", "저장 중…", true);
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
    }
    paintLastSnapshot(await window.API.client(editingSlug));
    say("metrics-msg", "지표를 저장했습니다.", true);
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
