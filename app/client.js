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
    clearDoc();               // 앞 매장 판독이 남으면 안 된다
    clearOpenub();            // 오픈업도 같은 이유로 비운다
    paintLastSnapshot(client);
    paintAdlogLink(client);

    // 지표 칸은 매장마다 새로 입력한다. 앞 매장 값이 남아 있으면
    // saveMetrics() 가 그걸 다음 매장에 그대로 얹는다 — #f-revenue 는
    // .manual-cost 라 가리기가 켜져 있으면 안 보이는 채로 남의 매장에
    // 저장된다.
    el("f-market-rank").value = "";
    el("f-revenue").value = "";
    el("f-keyword").value = "";
    // 평소엔 애드로그 PDF 로 받는다. 플레이스 직접 긁기는 그게 안 될 때만
    // 손으로 켜는 예외라 매장을 열 때마다 꺼진 채로 시작해야 한다.
    el("f-fetch-place").checked = false;
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

  // #metrics(지표)와 #doc(자료 판독)은 같은 생명주기를 산다 — 둘 다
  // 저장된 매장에서만 켜진다. 규칙을 한 곳에서만 관리한다 — 두 벌로
  // 나뉘면(open()·saveClient() 에 흩어지면) 한쪽만 고치고 잊는 사고가
  // 난다(I-5).
  function lock(disabled) {
    for (const id of ["metrics", "doc", "openub", "adlog"]) {
      if (disabled) el(id).setAttribute("disabled", "");
      else el(id).removeAttribute("disabled");
    }
  }

  async function open(slug) {
    editingSlug = slug || null;
    el("panel-title").textContent = slug ? "매장 정보" : "새 매장";
    say("client-msg", "");
    say("metrics-msg", "");
    // 앞 매장에서 띄운 후보가 남은 채 다음 매장이 열리면 남의 플레이스를
    // 잇게 된다 — 매장을 열 때마다 반드시 다시 감춘다.
    adlogItems = [];
    el("adlog-candidates").setAttribute("hidden", "");
    el("adlog-link").setAttribute("hidden", "");
    say("adlog-msg", "");
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

    // 판독 준비 상태(키 유무)는 잠금과 다른 축이라 따로 확인한다 — 잠금
    // 자체는 lock() 이 #doc 도 함께 맡는다(맨 위 lock(!slug), 실패 시
    // 아래 lock(true) 를 그대로 탄다).
    // fill() 뒤에 둔다: fill() 이 clearDoc() 을 불러 doc-msg 를 비우므로,
    // 그보다 먼저 메시지를 쓰면 이 자리에서 바로 지워진다(신규 등록도
    // fill({}) 을, 기존 매장 편집은 fill({}) 과 fill(client) 를 두 번
    // 부른다 — 둘 다 지나간 뒤에 써야 남는다).
    try {
      const { 준비됨 } = await window.API.readDocReady();
      el("doc-file").disabled = !준비됨;
      el("openub-file").disabled = !준비됨;
      if (!준비됨) {
        say("doc-msg", "판독 키가 없습니다. 손으로 입력하십시오.");
        say("openub-msg", "판독 키가 없습니다. 손으로 입력하십시오.");
      }
    } catch (err) {
      el("doc-file").disabled = true;
      el("openub-file").disabled = true;
      say("doc-msg", "판독 준비 상태를 확인하지 못했습니다.");
      say("openub-msg", "판독 준비 상태를 확인하지 못했습니다.");
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
        // 폼에 없는 칸은 다른 경로가 쓴 자료다 — 스냅샷(수집)·오픈업(판독)·
        // 애드로그(연결). 폼 값만 보내면 서버가 client.json 을 통째로
        // 덮어써서 그게 조용히 날아간다. 한때 스냅샷만 골라 살렸는데,
        // 칸이 하나 늘 때마다 여기를 고쳐야 했고 오픈업은 그 사이에
        // 빠졌다(Task 8 리뷰에서 드러났다).
        //
        // before 를 바닥에 깔고 폼 값을 그 위에 편다. formData() 는 폼
        // 칸을 빈 값까지 전부 돌려주므로 폼 칸은 언제나 폼이 이긴다 —
        // 사람이 지운 값은 빈 값으로 덮인다. 메모도 폼의 몫이라 이 순서로
        // 방금 고친 메모가 되돌아가지 않는다.
        const before = await window.API.client(editingSlug);
        await window.API.saveClient(editingSlug, {
          ...before, ...data, slug: editingSlug,
        });
      } else {
        const made = await window.API.createClient(data);
        editingSlug = made.slug;
      }
    } catch (err) {
      say("client-msg", err.message);
      return;
    }

    // 신규 등록은 open(null) 시점엔 slug 가 없어 #metrics·#doc 이 잠긴
    // 채로 열렸다. 저장으로 slug 가 생겼으니 lock(false) 로 둘 다 푼다.
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

  /* 애드로그 연결 — 등록된 플레이스를 골라 매장에 잇는다.

     등록(슬롯 소비)은 여기서 안 한다. 슬롯은 멤버십에서 나오고 삭제에
     월 한도가 있어, 도구가 마음대로 늘리면 되돌리기가 어렵다. 새
     키워드는 애드로그 화면에서 사람이 넣는다. */

  let adlogItems = [];

  function paintAdlogLink(client) {
    const 연결 = (client && client.애드로그) || null;
    if (!연결 || !연결.플레이스ID) {
      el("adlog-linked").textContent = "연결 안 됨";
      el("adlog-sync").disabled = true;
      return;
    }
    const n = (연결.키워드 || []).length;
    el("adlog-linked").textContent =
      `${연결.플레이스명 || 연결.플레이스ID} · 키워드 ${n}개`;
    el("adlog-sync").disabled = n === 0;
  }

  function paintCandidates(이름) {
    // 플레이스 하나에 키워드가 여럿이다. 매장 단위로 접어 보여준다.
    const byPlace = new Map();
    for (const it of adlogItems) {
      const key = String(it.place_id);
      if (!byPlace.has(key)) {
        byPlace.set(key, { place_id: key, place_name: it.place_name, 키워드: [] });
      }
      byPlace.get(key).키워드.push({ api_no: it.api_no, keyword: it.keyword });
    }

    // 이름이 겹치는 후보를 위로. 206 곳을 눈으로 훑게 두면 아무도 안 쓴다.
    const 점수 = (p) => (이름 && p.place_name && p.place_name.includes(이름) ? 0
      : 이름 && p.place_name && 이름.includes(p.place_name.split(" ")[0]) ? 1 : 2);
    const 후보 = [...byPlace.values()].sort(
      (a, b) => 점수(a) - 점수(b) || a.place_name.localeCompare(b.place_name));

    const box = el("adlog-candidates");
    box.innerHTML = "";
    for (const p of 후보) {
      const option = document.createElement("option");
      option.value = p.place_id;
      option.textContent = `${p.place_name} · 키워드 ${p.키워드.length}개`;
      box.appendChild(option);
    }
    box.removeAttribute("hidden");
    el("adlog-link").removeAttribute("hidden");

    // 플레이스URL 이 이미 있으면 그 자리를 미리 골라 둔다.
    const url = el("f-place-url").value || "";
    const 아이디 = (url.match(/(\d{6,})/) || [])[1];
    if (아이디 && byPlace.has(아이디)) box.value = 아이디;
    else if (후보.length) box.value = 후보[0].place_id;
  }

  async function findAdlog() {
    const button = el("adlog-find");
    button.disabled = true;
    say("adlog-msg", "");
    try {
      const got = await window.API.adlogPlaces(false);
      adlogItems = got.items || [];
      paintCandidates(el("f-name").value.trim());
      say("adlog-msg", `등록된 플레이스 ${new Set(adlogItems.map((i) => i.place_id)).size}곳`, true);
    } catch (err) {
      say("adlog-msg", err.message);
    } finally {
      button.disabled = false;
    }
  }

  async function linkAdlog() {
    if (!editingSlug) return;
    const 아이디 = el("adlog-candidates").value;
    const 묶음 = adlogItems.filter((i) => String(i.place_id) === 아이디);
    if (!묶음.length) return;

    // 잇는 동안 이 칸을 비워 둔다 — 앞선 「등록된 플레이스 N곳」이 남아
    // 있으면 화면을 기다리는 쪽도, 사람도 이미 끝난 걸로 읽는다.
    // saveMetrics() 가 같은 이유로 그렇게 돼 있다.
    say("adlog-msg", "");
    const button = el("adlog-link");
    button.disabled = true;
    try {
      const client = await window.API.client(editingSlug);
      const 애드로그 = {
        플레이스ID: 아이디,
        플레이스명: 묶음[0].place_name,
        연결시각: new Date().toISOString().slice(0, 19),
        키워드: 묶음.map((i) => ({ api_no: i.api_no, keyword: i.keyword })),
      };
      // 빈 칸만 채운다 — 손으로 고친 값을 되돌리지 않는다.
      const 갱신 = { ...client, 애드로그 };
      if (!(client.플레이스URL || "").trim()) {
        갱신.플레이스URL = `https://m.place.naver.com/restaurant/${아이디}/home`;
      }
      await window.API.saveClient(editingSlug, 갱신);

      el("f-place-url").value = 갱신.플레이스URL || "";
      paintAdlogLink(갱신);
      el("adlog-candidates").setAttribute("hidden", "");
      el("adlog-link").setAttribute("hidden", "");
      say("adlog-msg", `${묶음[0].place_name} 에 이었습니다.`, true);
    } catch (err) {
      say("adlog-msg", err.message);
    } finally {
      button.disabled = false;
    }
  }

  async function syncAdlog() {
    if (!editingSlug) return;
    const button = el("adlog-sync");
    button.disabled = true;
    say("adlog-msg", "");
    try {
      const got = await window.API.adlogSync(editingSlug);
      const 꼬리 = got.경고 ? ` (${got.경고})` : "";
      say("adlog-msg", `키워드 ${got.갱신}개를 갱신했습니다.${꼬리}`, true);
      paintLastSnapshot(await window.API.client(editingSlug));
    } catch (err) {
      say("adlog-msg", err.message);
    } finally {
      button.disabled = false;
    }
  }

  /* 자료 판독 — 애드로그 종합분석 PDF 를 값으로 바꾼다.

     판독은 화면을 채우기만 한다. 저장은 사람이 「판독값 저장」을 누를 때
     일어난다. 1,082 를 108 로 읽는 날이 오는데, 그게 조용히 제안서까지
     가면 안 된다.

     미리보기를 띄우지 않는다 — 같은 칸에 오픈업 캡처가 들어올 때 그
     그림에는 월매출이 박혀 있고, 「가리기」는 그림을 못 지운다. */

  let reading = null;

  function clearDoc() {
    reading = null;
    el("doc-result").innerHTML = "";
    say("doc-msg", "");
    el("doc-warn").textContent = "";
    el("apply-doc").disabled = true;
    el("doc-file").value = "";
  }

  function paintReading(got) {
    const r = got.판독 || {};
    const rows = [["플레이스명", r.플레이스명], ["방문자리뷰", r.방문자리뷰],
                  ["블로그리뷰", r.블로그리뷰], ["저장수", r.저장수],
                  ["총키워드", r.총키워드], ["TOP3", r.TOP3], ["TOP10", r.TOP10]];
    const dl = rows.filter(([, v]) => v !== null && v !== undefined && v !== "")
      .map(([k, v]) => `<dt>${window.Util.escapeHtml(k)}</dt>` +
                       `<dd>${window.Util.escapeHtml(String(v))}</dd>`).join("");
    const li = (r.순위 || []).map((x) =>
      `<li><span>${window.Util.escapeHtml(x.키워드)}</span>` +
      `<span>${window.Util.escapeHtml(String(x.순위))}위</span></li>`).join("");
    el("doc-result").innerHTML = `<dl>${dl}</dl><ul>${li}</ul>`;
    el("doc-warn").textContent = (got.경고 || []).join(" ");
    if (got.불일치) say("doc-msg", got.불일치);
    el("apply-doc").disabled = !got.저장가능;
    reading = got.저장가능 ? r : null;
  }

  async function readDoc(files) {
    // 응답이 오는 사이 패널이 닫히고 다른 매장이 열리면 editingSlug 가
    // 바뀐다. 그 시점의 slug 를 잡아 두고, 응답을 적용하기 전에 아직도
    // 같은 매장인지 다시 확인한다 — 다르면 A 의 판독값이 B 화면에 그려진다.
    const forSlug = editingSlug;
    say("doc-msg", "");
    el("doc-warn").textContent = "";
    el("doc-result").innerHTML = "";
    el("apply-doc").disabled = true;

    if (files.length > 6) {
      say("doc-msg", "캡처는 6장까지 넣을 수 있습니다.");
      el("doc-file").value = "";
      return;
    }

    el("doc-file").disabled = true;
    try {
      // 조회수는 순위 추이 표에, 리뷰 목록은 기본정보 화면에 있다.
      // 여러 장을 함께 보내야 한 매장의 그림이 맞춰진다.
      const 캡처 = [];
      for (const file of files) {
        const dataUrl = await new Promise((ok, no) => {
          const fr = new FileReader();
          fr.onload = () => ok(fr.result);
          fr.onerror = () => no(new Error("파일을 읽지 못했습니다."));
          fr.readAsDataURL(file);
        });
        캡처.push({ 파일명: file.name,
                    내용: String(dataUrl).split(",")[1] || "" });
      }
      const got = await window.API.readDoc({ slug: forSlug, 캡처 });
      if (editingSlug !== forSlug) return;   // 그 사이 매장이 바뀌었다 — 조용히 버린다
      paintReading(got);
    } catch (err) {
      if (editingSlug !== forSlug) return;
      say("doc-msg", err.message);
    } finally {
      if (editingSlug === forSlug) el("doc-file").disabled = false;
    }
  }

  async function applyDoc() {
    const forSlug = editingSlug;   // readDoc() 과 같은 이유로 잡아 둔다
    const button = el("apply-doc");
    button.disabled = true;
    try {
      await window.API.applyDoc({ slug: forSlug, 판독: reading });
      if (editingSlug !== forSlug) return;
      say("doc-msg", "판독값을 저장했습니다.", true);
      // 판독이 플레이스URL·업종·스냅샷을 바꿨다. 폼을 다시 읽어 온다.
      // 여기도 왕복이다 — 기다리는 사이 매장이 또 바뀔 수 있으니 같은
      // 검사를 한 번 더 건다. forSlug 로 요청해 처음부터 끝까지 "내가
      // 요청한 그 매장" 하나만 본다.
      const client = await window.API.client(forSlug);
      if (editingSlug !== forSlug) return;
      fill(client);
      window.Summary.applyConcealment();
    } catch (err) {
      if (editingSlug !== forSlug) return;
      say("doc-msg", err.message);
      button.disabled = false;
    }
  }

  /* 오픈업 캡처 판독.

     애드로그와 같은 원칙이다 — 화면을 채우기만 하고, 저장은 사람이
     누른다. 미리보기도 띄우지 않는다.

     오픈업은 스냅샷이 아니라 매장 파일의 월별 목록에 쌓인다. 스냅샷으로
     쌓으면 제안서가 마지막 스냅샷만 읽는 탓에 애드로그 리뷰수·순위가
     통째로 사라진다. */

  let openubReading = null;

  function clearOpenub() {
    openubReading = null;
    el("openub-result").innerHTML = "";
    say("openub-msg", "");
    el("apply-openub").disabled = true;
    el("openub-file").value = "";
  }

  function 만원(n) {
    return n === null || n === undefined
      ? "" : `${Math.round(n / 10000).toLocaleString()}만`;
  }

  function paintOpenub(got) {
    const r = got.판독 || {};
    const rows = [
      ["기준월", r.기준월 ? `${r.기준월}월` : null],
      ["추정 매출", r.매출하한 && r.매출상한
        ? `${만원(r.매출하한)} ~ ${만원(r.매출상한)}원` : null],
      ["주 고객", r.성별최다 ? `${r.성별최다} ${r.성별최다비율}%` : null],
      ["최다 연령", r.연령최다 ? `${r.연령최다} ${r.연령최다비율}%` : null],
      ["최다 요일", r.요일최다 ? `${r.요일최다} ${r.요일최다비율}%` : null],
      ["평일 비중", r.평일비율 === null || r.평일비율 === undefined
        ? null : `${r.평일비율}%`],
      ["최다 시간대", r.시간대최다 ? `${r.시간대최다} ${r.시간대최다비율}%` : null],
    ];
    // 매출 줄에는 「가리기」가 걸린다. 캡처에 박힌 월매출은 미팅 자리에서
    // 보일 이유가 없다 — 매장 준비 패널의 월매출 칸과 같은 규칙이다.
    const dl = rows.filter(([, v]) => v)
      .map(([k, v]) => {
        const 내부 = k === "추정 매출" ? ' class="internal-only"' : "";
        return `<dt${내부}>${window.Util.escapeHtml(k)}</dt>` +
               `<dd${내부}>${window.Util.escapeHtml(v)}</dd>`;
      }).join("");
    const 못읽음 = rows.filter(([, v]) => !v).map(([k]) => k);
    el("openub-result").innerHTML = `<dl>${dl}</dl>`;
    if (got.불일치) say("openub-msg", got.불일치);
    else if (못읽음.length) say("openub-msg", `못 읽은 항목: ${못읽음.join(" · ")}`);
    el("apply-openub").disabled = !got.저장가능;
    openubReading = got.저장가능 ? r : null;
    // 판독 결과를 새로 그렸다. 가리기가 켜져 있으면 다시 입힌다 —
    // 안 그러면 가린 상태에서 캡처를 넣는 순간 매출이 드러난다.
    window.Summary.applyConcealment();
  }

  async function readOpenub(files) {
    // readDoc() 과 같은 이유로 요청 시점의 slug 를 잡아 둔다 — 응답이
    // 오는 사이 다른 매장이 열리면 A 의 판독값이 B 화면에 그려진다.
    const forSlug = editingSlug;
    say("openub-msg", "");
    el("openub-result").innerHTML = "";
    el("apply-openub").disabled = true;

    if (files.length > 6) {
      say("openub-msg", "캡처는 6장까지 넣을 수 있습니다.");
      el("openub-file").value = "";
      return;
    }

    el("openub-file").disabled = true;
    try {
      const 캡처 = [];
      for (const file of files) {
        const dataUrl = await new Promise((ok, no) => {
          const fr = new FileReader();
          fr.onload = () => ok(fr.result);
          fr.onerror = () => no(new Error("파일을 읽지 못했습니다."));
          fr.readAsDataURL(file);
        });
        캡처.push({ 파일명: file.name,
                    내용: String(dataUrl).split(",")[1] || "" });
      }
      const got = await window.API.readOpenub({ slug: forSlug, 캡처 });
      if (editingSlug !== forSlug) return;
      paintOpenub(got);
    } catch (err) {
      if (editingSlug !== forSlug) return;
      say("openub-msg", err.message);
    } finally {
      if (editingSlug === forSlug) el("openub-file").disabled = false;
    }
  }

  async function applyOpenub() {
    const forSlug = editingSlug;
    const button = el("apply-openub");
    button.disabled = true;
    try {
      await window.API.applyOpenub({ slug: forSlug, 판독: openubReading });
      if (editingSlug !== forSlug) return;
      say("openub-msg", "판독값을 저장했습니다.", true);
    } catch (err) {
      if (editingSlug !== forSlug) return;
      say("openub-msg", err.message);
      button.disabled = false;
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

    el("doc-file").addEventListener("change", (e) => {
      const files = [...(e.target.files || [])];
      if (files.length) readDoc(files);
    });
    el("apply-doc").addEventListener("click", applyDoc);

    el("openub-file").addEventListener("change", (e) => {
      const files = [...(e.target.files || [])];
      if (files.length) readOpenub(files);
    });
    el("apply-openub").addEventListener("click", applyOpenub);

    el("adlog-find").addEventListener("click", findAdlog);
    el("adlog-link").addEventListener("click", linkAdlog);
    el("adlog-sync").addEventListener("click", syncAdlog);
  });
})();
