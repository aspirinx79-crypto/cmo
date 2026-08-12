/* 서버 호출 래퍼. fetch 세부를 화면 코드에서 감춘다. */
(function () {
  async function get(path) {
    const res = await fetch(path);
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const err = new Error(detail.오류 || `${path} → ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const err = new Error(detail.오류 || `${path} → ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  window.API = {
    products: () => get("/api/products"),
    presets: () => get("/api/presets"),
    clients: () => get("/api/clients"),
    client: (slug) => get(`/api/clients/${encodeURIComponent(slug)}`),
    planMonths: (slug) => get(`/api/clients/${encodeURIComponent(slug)}/plans`),
    plan: (slug, month) =>
      get(`/api/clients/${encodeURIComponent(slug)}/plans/${month}`),
    savePlan: (slug, month, plan, force) =>
      post(`/api/clients/${encodeURIComponent(slug)}/plans/${month}${force ? "?force=1" : ""}`, plan),
    copyPlan: (slug, month, 대상월) =>
      post(`/api/clients/${encodeURIComponent(slug)}/plans/${month}/copy`, { 대상월 }),
    summary: (항목, 계약가) => post("/api/summary", { 항목, 계약가 }),
    proposal: (slug, 월) => post("/api/proposal", { slug, 월 }),
    quote: (slug, 월, 부가세별도, 내역펼침) =>
      post("/api/quote", { slug, 월, 부가세별도, 내역펼침 }),
    createClient: (data) => post("/api/clients", data),
    saveClient: (slug, data) => post(`/api/clients/${encodeURIComponent(slug)}`, data),
    collect: (body) => post("/api/collect", body),
    readDocReady: () => get("/api/read-doc/ready"),
    readDoc: (body) => post("/api/read-doc", body),
    applyDoc: (body) => post("/api/read-doc/apply", body),
    readOpenub: (body) => post("/api/read-openub", body),
    applyOpenub: (body) => post("/api/read-openub/apply", body),
  };
})();
