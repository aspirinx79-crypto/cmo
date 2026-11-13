// 영업의 본질 - 마케팅 영업 기초 교육 자료 (초안)
// 실행: NODE_PATH=<pptxgenjs가 설치된 node_modules> node build_sales_deck.js [출력파일]
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.PPTX_APPLY_THEME ||
  "/root/.claude/skills/synced/1a62ff30-a17b-4a9d-bb46-a287bcb80359_f6686bbd-ce69-4d88-ac53-ac3e093346d8/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "영업의_본질_교육자료.pptx";
const FONT = "맑은 고딕";
const THEME = {
  name: "Sales Essence",
  headFontFace: FONT,
  bodyFontFace: FONT,
  colors: {
    dk1: "1C2430", lt1: "FFFFFF", dk2: "1F2A37", lt2: "F2F4F7",
    accent1: "FF6B2C", accent2: "2BB673", accent3: "3D7BD9", accent4: "FFB547",
    accent5: "8B5CF6", accent6: "8A94A6", hlink: "3D7BD9", folHlink: "1F2A37",
  },
};
const HEX = THEME.colors;
const iconCache = {};
async function icon(name, color) {
  const k = name + color;
  if (!iconCache[k]) {
    const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: "#" + color, size: "256" }));
    iconCache[k] = "image/png;base64," + (await sharp(Buffer.from(svg)).png().toBuffer()).toString("base64");
  }
  return iconCache[k];
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
  pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
  pres.title = "영업의 본질";
  const C = pres.SchemeColor;
  const T = { isTextBox: true, margin: 0 };

  pres.defineSlideMaster({
    title: "COVER", background: { color: HEX.dk2 },
    objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.5, w: 8.8, h: 1.5, fontSize: 44, bold: true, color: C.background1, align: "left", valign: "top", margin: 0 }, text: "" } }],
  });
  pres.defineSlideMaster({
    title: "SECTION", background: { color: HEX.dk2 },
    objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.3, w: 8.8, h: 1.0, fontSize: 38, bold: true, color: C.background1, align: "left", valign: "middle", margin: 0 }, text: "" } }],
  });
  pres.defineSlideMaster({
    title: "CONTENT", background: { color: HEX.lt1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 8.8, h: 0.7, fontSize: 28, bold: true, color: C.text2, align: "left", valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "영업의 본질  |  마케팅 영업 기초 교육", options: { x: 0.6, y: 5.22, w: 5, h: 0.25, fontSize: 10, color: C.accent6, margin: 0 } } },
    ],
    slideNumber: { x: 9.0, y: 5.22, w: 0.4, h: 0.25, fontSize: 10, color: C.accent6, align: "right" },
  });

  let section = "";
  const content = (title, notes) => {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
    s.addText(title, { placeholder: "title" });
    if (notes) s.addNotes(notes);
    return s;
  };
  const sub = (s, text, y = 1.08) =>
    s.addText(text, { ...T, x: 0.6, y, w: 8.8, h: 0.4, fontSize: 15, color: C.text1 });
  const takeaway = (s, text, y = 4.55) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 8.8, h: 0.5, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "takeawayBox" });
    s.addImage({ data: await_icons.bolt, x: 0.78, y: y + 0.13, w: 0.24, h: 0.24, altText: "핵심" });
    s.addText(text, { ...T, x: 1.15, y, w: 8.1, h: 0.5, fontSize: 15, bold: true, color: C.accent1, valign: "middle" });
  };
  const circleIcon = async (s, name, x, y, d, fill = C.accent1, iconColor = HEX.lt1) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, objectName: "iconCircle" });
    const p = d * 0.27;
    s.addImage({ data: await icon(name, iconColor), x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, altText: name });
  };
  // cards: [icon, head, body]
  const cards = async (s, items, { cols = items.length, y = 1.6, h = 2.7, fill = C.background2, accent = C.accent1 } = {}) => {
    const gap = 0.3, w = (8.8 - gap * (cols - 1)) / cols;
    const rows = Math.ceil(items.length / cols), rh = (h - gap * (rows - 1)) / rows;
    for (let i = 0; i < items.length; i++) {
      const x = 0.6 + (i % cols) * (w + gap), yy = y + Math.floor(i / cols) * (rh + gap);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: yy, w, h: rh, fill: { color: fill }, rectRadius: 0.1, objectName: "card" + i });
      const [ic, head, body] = items[i];
      const horizontal = rh < 1.5;
      if (horizontal) {
        await circleIcon(s, ic, x + 0.22, yy + (rh - 0.6) / 2, 0.6, accent);
        s.addText(head, { ...T, x: x + 1.0, y: yy + 0.14, w: w - 1.15, h: 0.4, fontSize: w < 3 ? 15 : 16, bold: true, color: C.text2 });
        s.addText(body, { ...T, x: x + 1.0, y: yy + 0.55, w: w - 1.15, h: rh - 0.65, fontSize: 13, color: C.text1, valign: "top" });
      } else {
        await circleIcon(s, ic, x + 0.25, yy + 0.25, 0.65, accent);
        s.addText(head, { ...T, x: x + 0.25, y: yy + 1.05, w: w - 0.45, h: 0.45, fontSize: 17, bold: true, color: C.text2 });
        s.addText(body, { ...T, x: x + 0.25, y: yy + 1.52, w: w - 0.45, h: rh - 1.65, fontSize: 13, color: C.text1, valign: "top" });
      }
    }
  };
  const compare = (s, L, R, { y = 1.5, h = 2.85 } = {}) => {
    const cols = [[L, C.accent6, C.background2], [R, C.accent1, "FFF1EA"]];
    cols.forEach(([[head, items], color, fill], i) => {
      const x = 0.6 + i * 4.55;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 4.25, h, fill: { color: fill }, rectRadius: 0.1, objectName: "compare" + i });
      s.addText(head, { ...T, x: x + 0.3, y: y + 0.2, w: 3.7, h: 0.45, fontSize: 18, bold: true, color });
      s.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
        { ...T, x: x + 0.3, y: y + 0.75, w: 3.7, h: h - 0.9, fontSize: 14, color: C.text1, valign: "top", paraSpaceAfter: 8 });
    });
  };
  const flow = async (s, steps, { y = 1.55, h = 2.7 } = {}) => {
    const n = steps.length, gap = 0.28, w = (8.8 - gap * (n - 1)) / n;
    for (let i = 0; i < n; i++) {
      const x = 0.6 + i * (w + gap);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "step" + i });
      s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + 0.2, w: 0.55, h: 0.55, fill: { color: i === n - 1 ? C.accent2 : C.accent1 }, objectName: "stepNum" + i });
      s.addText(String(i + 1), { ...T, x: x + 0.2, y: y + 0.2, w: 0.55, h: 0.55, fontSize: 20, bold: true, color: C.background1, align: "center", valign: "middle" });
      s.addText(steps[i][0], { ...T, x: x + 0.2, y: y + 0.9, w: w - 0.35, h: 0.45, fontSize: 16, bold: true, color: C.text2 });
      s.addText(steps[i][1], { ...T, x: x + 0.2, y: y + 1.38, w: w - 0.35, h: h - 1.5, fontSize: 13, color: C.text1, valign: "top" });
      if (i < n - 1) s.addImage({ data: await icon("FaChevronRight", HEX.accent6), x: x + w + 0.06, y: y + h / 2 - 0.1, w: 0.16, h: 0.2, altText: "다음" });
    }
  };
  const sectionSlide = (num, title, subtitle, notes) => {
    section = title;
    pres.addSection({ title });
    const s = pres.addSlide({ masterName: "SECTION", sectionTitle: title });
    s.addText(num, { ...T, x: 0.6, y: 1.25, w: 3, h: 1.0, fontSize: 60, bold: true, color: C.accent1 });
    s.addText(title, { placeholder: "title" });
    s.addText(subtitle, { ...T, x: 0.6, y: 3.35, w: 8.8, h: 0.5, fontSize: 18, color: "C9D1DC" });
    if (notes) s.addNotes(notes);
    return s;
  };
  const await_icons = { bolt: await icon("FaBolt", HEX.accent1) };

  // =================== 오프닝 ===================
  section = "오프닝";
  pres.addSection({ title: section });
  let s = pres.addSlide({ masterName: "COVER", sectionTitle: section });
  s.addText("마케팅 영업 기초 교육", { ...T, x: 0.6, y: 0.8, w: 6, h: 0.45, fontSize: 18, bold: true, color: C.accent1 });
  s.addText("영업의 본질", { placeholder: "title" });
  s.addText("하는 만큼 성취하는 일 — 상품이 아니라 '나'를 믿게 만드는 법", { ...T, x: 0.6, y: 2.55, w: 8.8, h: 0.5, fontSize: 20, color: "C9D1DC" });
  s.addText("강사  OOO 대표  |  20년 군 복무 → 마케팅 회사 창업", { ...T, x: 0.6, y: 4.5, w: 8.8, h: 0.4, fontSize: 14, color: C.background1 });
  s.addNotes("[보완 필요: 강사 이름, 회사명] 인사 후 시작. '오늘은 상품을 파는 기술이 아니라, 영업이라는 일의 본질을 이야기하려고 합니다.'");

  s = content("오늘 함께 나눌 이야기", "전체 흐름을 먼저 보여 줍니다. 약 90분 + 질의응답 기준. 파트별로 15~20분씩.");
  const agenda = [
    ["01", "왜 영업인가", "20년 군 생활에서 영업으로"],
    ["02", "마케팅·영업의 본질", "Market + ing, 알려야 팔린다"],
    ["03", "신뢰를 만드는 3가지", "첫인상 · 자신감 · 전문성"],
    ["04", "찾아오게 만드는 영업", "모임과 소개의 힘"],
    ["05", "영업 실전 프로세스", "만남부터 재계약까지"],
  ];
  agenda.forEach(([n, h, b], i) => {
    const y = 1.3 + i * 0.72;
    s.addText(n, { ...T, x: 0.6, y, w: 0.9, h: 0.6, fontSize: 30, bold: true, color: C.accent1, valign: "middle" });
    s.addText(h, { ...T, x: 1.6, y, w: 3.6, h: 0.6, fontSize: 19, bold: true, color: C.text2, valign: "middle" });
    s.addText(b, { ...T, x: 5.2, y, w: 4.2, h: 0.6, fontSize: 15, color: C.text1, valign: "middle" });
  });

  // =================== 01 왜 영업인가 ===================
  sectionSlide("01", "왜 영업인가", "안정의 20년, 그리고 성취의 시작", "강사 본인의 이야기로 공감대를 만드는 파트입니다.");

  s = content("20년 군 생활이 내게 준 것과 주지 않은 것",
    "20년 동안 군 생활을 했습니다. 1년 뒤, 5년 뒤 월급이 얼마인지 알 수 있는 안정감은 있었습니다. 그런데 '내가 이걸 해서 이런 성과를 냈다'는 성취감은 하나도 없었습니다. 요즘 사람들은 직업을 고를 때 꿈과 미래를 봅니다. 월급만으로는 몇십억 하는 서울 아파트는 절대 살 수 없겠다는 생각도 들었습니다.");
  compare(s, ["군 생활 20년이 준 것", ["따박따박 들어오는 월급", "1년 뒤, 5년 뒤가 예측되는 안정감", "연봉 약 6,500만 원 — 생활과 저축 가능"]],
    ["주지 않은 것", ["내가 한 일에 대한 성과와 성취감", "꿈과 미래에 대한 기대", "월급만으로는 닿을 수 없는 목표 (서울 아파트)"]]);
  takeaway(s, "안정은 있었지만, '내가 해냈다'는 느낌은 없었다");

  s = content("숫자로 보는 변화",
    "군 시절 연봉이 약 6,500만 원이었습니다. 지금은 한 달에 6,500만 원이 넘는 매출을 내고 있습니다. 1년 12개월 동안 할 일을 한 달에, 저를 믿고 대표님들이 맡겨 주고 계신 겁니다. 자랑이 아니라, 저를 믿고 계속 유지해 주시는 대표님들 덕분입니다.");
  const stats = [["6,500만 원", "군 시절 '연봉'", C.accent6], ["6,500만 원↑", "지금의 '월' 매출", C.accent1], ["80~90%", "만남 대비 계약률", C.accent2]];
  stats.forEach(([n, l, col], i) => {
    const x = 0.6 + i * 3.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.45, w: 2.8, h: 2.3, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "stat" + i });
    s.addText(n, { ...T, x, y: 1.75, w: 2.8, h: 0.9, fontSize: 30, bold: true, color: col, align: "center", valign: "middle" });
    s.addText(l, { ...T, x, y: 2.75, w: 2.8, h: 0.5, fontSize: 16, color: C.text1, align: "center" });
  });
  takeaway(s, "1년 동안 할 일을 한 달에 — 나를 믿어 주는 고객 덕분", 4.2);

  s = content("영업은 '하는 만큼' 돌아오는 일",
    "지금은 눈 떠서 자기 전까지 일 생각을 합니다. '그렇게 살면 힘들지 않아요?' 하시는데, 힘든 것보다 재미있습니다. 결과가 나오고 있으니까요. 하는 만큼 버는 것, 그게 자영업·사업·영업의 가장 큰 장점입니다.");
  await cards(s, [
    ["FaSun", "아침이 즐겁다", "눈 뜨는 순간부터 오늘 할 일이 기대된다"],
    ["FaChartLine", "결과가 보인다", "한 만큼 계약과 매출로 바로 돌아온다"],
    ["FaSmile", "그래서 행복하다", "힘듦보다 재미가 크다 — 성취감의 힘"],
  ], { h: 2.6 });
  takeaway(s, "영업의 최고 보상은 돈이 아니라 '성취감'이다");

  s = content("\"돈 많이 버시네요?\" — 당연한 계산입니다",
    "자영업자가 한 달 700~800만 원 벌면 '돈 많이 버시네요' 합니다. 그런데 계산해 보면 당연합니다. 직장인은 하루 8시간, 주 5일, 주 40시간, 한 달 약 160시간 일합니다. 영업하는 사람은 하루 최소 12~15시간, 주말도 없습니다. 일한 시간이 두세 배니 더 버는 게 당연합니다.");
  s.addChart(pres.charts.BAR, [{ name: "월 근무시간", labels: ["직장인·공무원\n(8시간×주5일)", "영업인\n(12시간×매일)", "영업인\n(15시간×매일)"], values: [160, 360, 450] }], {
    x: 0.6, y: 1.2, w: 5.6, h: 3.9, barDir: "col", chartColors: [HEX.accent6, HEX.accent1, HEX.accent1],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"시간"', dataLabelFontSize: 13, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    showLegend: false, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    catAxisLabelColor: HEX.dk1, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", barGapWidthPct: 60,
    showTitle: true, title: "한 달 일하는 시간 (30일 기준)", titleFontSize: 14, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
  });
  s.addText([
    { text: "일한 시간이 2~3배", options: { fontSize: 22, bold: true, color: C.accent1, breakLine: true } },
    { text: "더 버는 것은 운이 아니라 당연한 결과입니다.", options: { fontSize: 15, color: C.text1, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "일을 안 하면 100만 원도 못 가져가고, 열심히 하면 1,000만~2,000만 원도 가져가는 구조.", options: { fontSize: 15, color: C.text1 } },
  ], { ...T, x: 6.5, y: 1.6, w: 2.9, h: 2.9, valign: "top" });

  s = content("영업 소득의 구조: 바닥도 천장도 내가 정한다",
    "월급은 정해져 있습니다. 영업은 바닥도 천장도 없습니다. 무섭기도 하지만, 그래서 기회입니다. 처음 시작하는 분들께 꼭 드리고 싶은 말: 처음엔 바닥을 경험할 수 있습니다. 그 시기를 버티는 사람이 천장을 봅니다.");
  compare(s, ["월급 구조", ["일한 만큼이 아니라 '정해진 만큼'", "1년 뒤, 5년 뒤 금액이 예측됨", "성과를 내도 보상은 비슷함"]],
    ["영업 구조", ["안 하면 월 100만 원도 어렵다", "하면 월 1,000만~2,000만 원도 가능", "결과가 곧 나의 평가 — 성취감"]]);
  takeaway(s, "영업은 '시간 × 노력 × 신뢰'가 그대로 수입이 되는 일");

  // =================== 02 본질 ===================
  sectionSlide("02", "마케팅·영업의 본질", "좋은 상품이 안 팔리는 이유", "마케팅과 영업이 무엇인지 정의하는 파트.");

  s = content("마케팅 = Market + ing",
    "마케팅은 Market에 ing가 붙은 말입니다. 시장이 계속 '진행되도록', 즉 사고팔기가 잘 일어나도록 돕는 모든 행동이 마케팅입니다. 광고만 마케팅이 아닙니다. 고객에게 알리고, 만나고, 신뢰를 쌓는 영업도 마케팅입니다.");
  s.addText("MARKET", { ...T, x: 0.6, y: 1.5, w: 3.6, h: 1.1, fontSize: 52, bold: true, color: C.text2, align: "center", valign: "middle" });
  s.addText("+", { ...T, x: 4.2, y: 1.5, w: 0.8, h: 1.1, fontSize: 48, bold: true, color: C.accent6, align: "center", valign: "middle" });
  s.addText("ING", { ...T, x: 5.0, y: 1.5, w: 2.4, h: 1.1, fontSize: 52, bold: true, color: C.accent1, align: "center", valign: "middle" });
  s.addText("시장", { ...T, x: 0.6, y: 2.6, w: 3.6, h: 0.4, fontSize: 16, color: C.text1, align: "center" });
  s.addText("진행되게", { ...T, x: 5.0, y: 2.6, w: 2.4, h: 0.4, fontSize: 16, color: C.text1, align: "center" });
  await circleIcon(s, "FaStore", 7.9, 1.6, 0.9, C.accent2);
  s.addText("거래가 일어나도록\n돕는 모든 행동", { ...T, x: 7.5, y: 2.55, w: 1.9, h: 0.7, fontSize: 13, bold: true, color: C.accent2, align: "center" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 3.45, w: 8.8, h: 0.9, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "def" });
  s.addText("마케팅이란, 시장(Market)이 계속 움직이도록(ing) 돕는 모든 행동이다.\n알리고, 만나고, 신뢰를 쌓는 '영업'도 마케팅의 한가운데에 있다.", { ...T, x: 0.9, y: 3.45, w: 8.3, h: 0.9, fontSize: 15, color: C.text2, valign: "middle" });

  s = content("마케팅이 필요 없는 산업은 없다",
    "뷰티, 패션은 물론이고 철강, 목수, 도배·장판, 건설 현장, 음식점까지. 우리나라에서 돌아가는 모든 산업은 '알려야' 팔립니다. 그래서 마케팅 영업은 어떤 업종의 대표님을 만나도 할 이야기가 있는 일입니다.");
  const inds = [["FaMagic", "뷰티"], ["FaTshirt", "패션"], ["FaUtensils", "음식점"], ["FaIndustry", "철강·제조"],
    ["FaHammer", "목수·인테리어"], ["FaPaintRoller", "도배·장판"], ["FaHardHat", "건설 현장"], ["FaEllipsisH", "그리고 모든 업종"]];
  for (let i = 0; i < 8; i++) {
    const x = 0.6 + (i % 4) * 2.25, y = 1.35 + Math.floor(i / 4) * 1.55;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.05, h: 1.35, fill: { color: i === 7 ? "FFF1EA" : C.background2 }, rectRadius: 0.1, objectName: "ind" + i });
    s.addImage({ data: await icon(inds[i][0], i === 7 ? HEX.accent1 : HEX.dk2), x: x + 0.78, y: y + 0.2, w: 0.5, h: 0.5, altText: inds[i][1] });
    s.addText(inds[i][1], { ...T, x, y: y + 0.82, w: 2.05, h: 0.4, fontSize: 15, bold: true, color: i === 7 ? C.accent1 : C.text2, align: "center" });
  }
  takeaway(s, "모든 사장님은 잠재 고객 — 업종보다 '알리는 일'이 공통분모", 4.55);

  s = content("\"우리 상품은 최고\"인데 왜 안 팔릴까?",
    "대표님들은 '내 상품은 어디 가도 최고야'라고 생각하십니다. 실제로 좋은 상품도 많습니다. 그런데 그 안에만 갇혀 있는 분들이 너무 많습니다. 아무리 좋아도 모르면 못 삽니다. 그걸 알려 주는 게 진짜, 찐입니다.");
  compare(s, ["갇혀 있는 상품", ["품질은 자신 있다", "그런데 아는 사람이 없다", "기다리면 손님이 올 거라 믿는다", "결과: 좋은데 안 팔린다"]],
    ["알려진 상품", ["품질에 '알림'이 더해진다", "필요한 사람에게 닿는다", "고객이 먼저 찾아온다", "결과: 좋아서 팔린다"]]);
  takeaway(s, "좋은 상품을 많은 사람에게 알려 팔리게 돕는 것 — 그것이 우리의 일");

  s = content("고객은 상품보다 '사람'을 산다",
    "[추가 제안 내용] 마케팅 상품은 회사마다 비슷해 보입니다. 블로그, 숏폼, 광고… 대표님 입장에서는 누구에게 맡겨도 비슷해 보이죠. 그래서 결정은 결국 '이 사람을 믿을 수 있나'로 내려집니다. 영업의 본질은 상품 설명이 아니라 신뢰를 쌓는 일입니다.");
  await cards(s, [
    ["FaBoxOpen", "상품은 비슷하다", "마케팅 상품은 어느 회사나 비슷해 보인다"],
    ["FaUserCheck", "결정은 사람이 한다", "\"이 사람에게 맡기면 되겠다\"는 믿음"],
    ["FaHandshake", "영업 = 신뢰 쌓기", "말이 아니라 준비·태도·결과로 증명"],
  ], { h: 2.6 });
  takeaway(s, "우리가 파는 것은 상품이 아니라 '믿음'이다");

  s = content("판매원과 영업 파트너의 차이",
    "[추가 제안 내용] 오늘 교육에서 가장 강조하고 싶은 장면입니다. 판매원은 내 상품을 설명하고, 파트너는 고객의 매출을 고민합니다. 고객은 판매원은 피하고, 파트너는 찾습니다.");
  compare(s, ["판매원", ["내 상품 이야기부터 꺼낸다", "이번 달 내 실적이 목표", "계약하면 끝", "고객이 피한다"]],
    ["영업 파트너", ["대표님의 고민부터 듣는다", "대표님 매출이 오르는 것이 목표", "계약은 관계의 시작", "고객이 찾아온다"]]);
  takeaway(s, "고객의 매출을 내 일처럼 고민하는 사람이 결국 선택받는다");

  // =================== 03 신뢰 3요소 ===================
  sectionSlide("03", "신뢰를 만드는 3가지", "계약률 80~90%의 비밀", "강사의 계약률이 높은 이유를 구체적으로 풀어 주는 파트.");

  s = content("나는 먼저 찾아가지 않는다",
    "제 계약률이 80~90%인 이유는, 제가 먼저 찾아가거나 먼저 제안하는 경우가 거의 없기 때문입니다. 대표님들이 저를 찾아오게 만들었습니다. 찾아온 사람은 이미 절반은 마음을 정하고 온 사람입니다.");
  compare(s, ["찾아가는 영업 (Push)", ["내가 먼저 연락하고 설득한다", "상대는 경계부터 한다", "가격 비교 대상이 된다", "계약률이 낮다"]],
    ["찾아오게 하는 영업 (Pull)", ["상대가 먼저 묻고 요청한다", "이미 신뢰를 갖고 온다", "'누구에게'가 아니라 '언제' 맡길지 고민", "계약률 80~90%"]]);
  takeaway(s, "목표는 '설득'이 아니라 '찾아오게 만드는 것'");

  s = content("처음엔 찾아가야 한다 — 단, '우위'를 갖고",
    "처음 시작할 때는 아무도 나를 모릅니다. 찾아갈 수밖에 없습니다. 이때 중요한 건, 찾아가더라도 상대보다 정보든 경험이든 겉으로 보이는 모습이든 '우세'가 있어야 한다는 것입니다. 이 세 가지가 신뢰를 만듭니다.");
  await cards(s, [
    ["FaUserTie", "① 첫인상", "단정한 외모 — 보기만 해도 '맡겨도 되겠다'"],
    ["FaEye", "② 자신감", "눈을 보고, 결과를 약속하는 태도"],
    ["FaBookOpen", "③ 전문성", "어떤 질문에도 막힘없는 준비"],
  ], { h: 2.6 });
  takeaway(s, "나를 모르는 상대에게는 '보이는 것'과 '아는 것'으로 신뢰를 준다");

  s = content("① 첫인상: 단정함은 실력의 첫 증거",
    "보험·영업하는 분들이 왜 정장을 입고 다닐까 처음엔 몰랐습니다. 이제는 압니다. 청바지에 구겨진 티셔츠를 입고 영업을 왔다면? 겪어 봐야 알겠지만, 보기만 해도 '잘 모를 것 같고, 맡기면 제대로 안 해 줄 것 같은' 이미지가 듭니다. 꼭 정장일 필요는 없습니다. 단정하면 됩니다.");
  compare(s, ["이렇게는 NO", ["구겨진 티셔츠, 낡은 청바지", "정리 안 된 머리, 지저분한 신발", "휴대폰만 보며 앉아 있기", "명함 없이 말로만 소개"]],
    ["이렇게 YES", ["다림질된 셔츠·깔끔한 재킷 (정장 필수 아님)", "단정한 머리, 깨끗한 신발", "바른 자세, 밝은 인사", "명함·자료를 준비해 건네기"]]);
  takeaway(s, "첫인상은 3초, 그 3초가 '들어 줄지 말지'를 정한다");

  s = content("② 자신감: \"맡겨 주시면 매출을 올리겠습니다\"",
    "대표님을 만나면 눈을 잘 쳐다보고, '저에게 맡겨 주시면 제대로 매출을 끌어올리겠습니다'라는 자신감을 보여 주세요. 자신감은 큰소리가 아니라 준비에서 나옵니다. 아래 문장을 소리 내어 연습해 봅시다.");
  await cards(s, [
    ["FaEye", "눈을 맞춘다", "말할 때도, 들을 때도 상대의 눈을 본다"],
    ["FaMicrophone", "말끝을 흐리지 않는다", "\"~인 것 같아요\" 대신 \"~입니다\""],
    ["FaBullseye", "결과로 말한다", "\"비슷한 매장에서 이렇게 올렸습니다\""],
  ], { y: 1.35, h: 2.3 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 3.9, w: 8.8, h: 1.1, fill: { color: "FFF1EA" }, rectRadius: 0.1, objectName: "practice" });
  s.addText([
    { text: "따라 해 보기", options: { fontSize: 13, bold: true, color: C.accent1, breakLine: true } },
    { text: "\"대표님, 이 부분은 제가 자신 있습니다. 맡겨 주시면 3개월 안에 숫자로 보여 드리겠습니다.\"", options: { fontSize: 16, bold: true, color: C.text2 } },
  ], { ...T, x: 0.9, y: 3.9, w: 8.3, h: 1.1, valign: "middle" });

  s = content("③ 전문성: 사장님들은 이미 많이 안다",
    "요즘은 정보가 너무 많이 공개되어 있습니다. 마케팅 회사만 검색해도 수십, 수백 곳이 나오고, 사장님들은 가만히 있어도 전화가 엄청 옵니다. 유튜브, 블로그에 정보도 넘칩니다. 그래서 우리가 전문가가 되지 않으면 신뢰가 생기지 않습니다. 대표님이 질문했는데 '그건 제가 모르는데요' 하면 그 순간 끝입니다.");
  await cards(s, [
    ["FaSearch", "검색하면 수백 곳", "마케팅 회사는 넘쳐난다 — 비교당하는 게 기본"],
    ["FaPhoneSlash", "하루에도 여러 통", "\"마케팅 회사인데요~\" 전화는 바로 끊긴다"],
    ["FaYoutube", "정보도 넘친다", "유튜브·블로그로 공부한 사장님이 많다"],
  ], { h: 2.6 });
  takeaway(s, "\"그건 제가 모르는데요\" — 이 한마디에 신뢰가 무너진다");

  s = content("전문가가 되기 위해 공부할 5가지",
    "[추가 제안 내용] '공부하라'는 말은 막연합니다. 구체적으로 무엇을 알아야 하는지 정리했습니다. 특히 4번, 만나기 전에 그 대표님 매장을 먼저 검색해 보고 가는 것만으로도 다른 영업인과 완전히 달라집니다.");
  await cards(s, [
    ["FaBox", "1. 내 상품", "가격·구성·효과·한계까지 막힘없이"],
    ["FaChessKnight", "2. 경쟁사", "다른 회사와 무엇이 다른지 한 문장으로"],
    ["FaStore", "3. 고객 업종", "그 업종의 성수기·고민·용어"],
    ["FaMapMarkedAlt", "4. 그 매장 자체", "만나기 전 검색·리뷰·SNS를 미리 확인"],
    ["FaChartBar", "5. 트렌드·사례", "플랫폼 변화, 실제 성과 숫자"],
    ["FaClipboardList", "+ 나만의 노트", "자주 받는 질문과 답을 정리해 두기"],
  ], { cols: 3, h: 3.0, y: 1.35 });
  takeaway(s, "준비한 만큼 막힘이 없고, 막힘이 없는 만큼 신뢰가 쌓인다", 4.6);

  s = content("모르는 질문을 받았을 때",
    "[추가 제안 내용] 아무리 준비해도 모르는 질문은 나옵니다. 그때 '모르는데요'로 끝내면 신뢰가 무너지고, 아는 척하면 나중에 더 크게 무너집니다. 정답은 '확인 후 약속한 시간 안에 답하기'입니다. 이렇게 하면 오히려 신뢰가 올라갑니다.");
  compare(s, ["이렇게 말하면 끝", ["\"그건 제가 모르는데요.\"", "\"그건 담당이 아니라서요.\"", "모르면서 아는 척 대충 답하기"]],
    ["이렇게 말하면 신뢰 UP", ["\"정확하게 확인해서 오늘 6시 전까지 답드리겠습니다.\"", "메모하는 모습을 보여 준다", "약속한 시간보다 먼저 답한다"]]);
  takeaway(s, "모르는 것은 약점이 아니다 — 약속을 지키지 않는 것이 약점이다");

  // =================== 04 찾아오게 만드는 영업 ===================
  sectionSlide("04", "찾아오게 만드는 영업", "사람이 있는 곳으로 가라", "모임과 소개를 통해 영업 기회를 만드는 파트.");

  s = content("기회는 사람이 있는 곳에 있다",
    "여자를 만나고 싶은데 맨날 남자만 있는 곳에 있으면 연애를 할 수 없겠죠. 비즈니스도 똑같습니다. 대표님들을 만나려면 대표님들이 모이는 곳에 가야 합니다. 저는 지금 이런 모임에 다니고 있습니다.");
  await cards(s, [
    ["FaUtensils", "중앙대 외식산업 최고위과정", "강남 — 외식업 대표님들과의 만남"],
    ["FaUniversity", "서울과기대 최고위과정", "카도 · 매주 목요일 — 다양한 업종 대표님"],
    ["FaCoffee", "BNI 조찬 모임", "매주 목요일 아침 — 소개 중심 비즈니스 모임"],
    ["FaChurch", "CBMC 기독실업인회", "격주 — 신앙을 가진 사업가 대표님들"],
  ], { cols: 2, h: 2.9, y: 1.3 });
  takeaway(s, "만나는 대표님이 많을수록 기회는 자연스럽게 생긴다", 4.5);

  s = content("모임에서 바로 영업하지 마라",
    "모임에 가자마자 영업을 하면 '영업하러 들어왔구나' 하고 마음을 닫습니다. 자연스럽게 친분을 쌓으면, 마케팅 이야기가 나올 때 대표님들이 먼저 저에게 물어봅니다. 그리고 '내 주변에 이런 사람이 필요하다는데 해 줄 수 있어?' 하고 소개도 해 주십니다.");
  await flow(s, [
    ["친분 쌓기", "영업 이야기 없이 사람으로 먼저 가까워진다"],
    ["도움 주기", "묻지 않아도 도움이 될 정보를 나눈다"],
    ["질문 받기", "\"마케팅은 어떻게 해야 해?\" 먼저 물어 온다"],
    ["소개 받기", "\"내 지인이 필요하다는데 해 줄 수 있어?\""],
  ]);
  takeaway(s, "모임은 판매하는 곳이 아니라, 신뢰를 저축하는 곳");

  s = content("소개가 끊이지 않는 사람의 습관",
    "[추가 제안 내용] BNI의 철학이 'Givers Gain(주는 사람이 얻는다)'입니다. 내가 먼저 소개해 주고, 먼저 도와주는 사람에게 소개가 돌아옵니다. 소개받은 건은 반드시 결과를 소개해 준 분께 보고하세요. 그래야 다음 소개가 옵니다.");
  await cards(s, [
    ["FaGift", "먼저 준다", "내가 먼저 다른 대표님을 소개하고 연결한다"],
    ["FaCalendarCheck", "꾸준히 간다", "한두 번이 아니라 매주·매달 빠지지 않고"],
    ["FaReply", "48시간 안에 연락", "명함 받은 분께 이틀 안에 인사 메시지"],
    ["FaThumbsUp", "결과를 보고한다", "소개해 준 분께 \"덕분에 잘 진행됐습니다\""],
  ], { cols: 2, h: 2.9, y: 1.3 });
  takeaway(s, "Givers Gain — 먼저 주는 사람에게 기회가 돌아온다", 4.5);

  s = content("30초 자기소개를 준비하라",
    "[추가 제안 내용] 모임에서는 자기소개 기회가 반드시 옵니다. 회사 이름만 말하면 기억에 남지 않습니다. '누구를, 어떻게 도와 어떤 결과를 냈는지'를 30초에 담으세요. 직접 써 보고 옆 사람과 연습하는 실습으로 진행하면 좋습니다.");
  await flow(s, [
    ["나는 누구", "\"외식업 매출을 올리는 마케터 OOO입니다\""],
    ["누구를 돕나", "\"손님이 없어 고민인 동네 매장 사장님\""],
    ["어떤 결과", "\"한 고깃집은 3개월 만에 예약이 두 배\""],
    ["이런 분 소개", "\"새로 오픈하는 매장이 있다면 연결해 주세요\""],
  ], { h: 2.5 });
  s.addText("실습: 나만의 30초 자기소개를 써 보고 옆 사람에게 말해 보기 (5분)", { ...T, x: 0.6, y: 4.3, w: 8.8, h: 0.5, fontSize: 15, bold: true, color: C.accent1 });

  s = content("온라인에서도 '찾아오게' 만들기",
    "[추가 제안 내용 — 강사님 실제 방법으로 보완 필요] 모임이 오프라인 신뢰라면, SNS는 온라인 신뢰입니다. 마케팅 영업인이 자기 자신을 마케팅하지 못하면 설득력이 없습니다. 내 성과 사례, 업무 일상을 꾸준히 올리면 처음 만나는 대표님도 이미 나를 알고 옵니다.");
  await cards(s, [
    ["FaInstagram", "SNS·숏폼", "일하는 모습, 현장, 노하우를 꾸준히"],
    ["FaBlog", "블로그", "성공 사례와 숫자를 글로 정리"],
    ["FaIdCard", "프로필·명함", "검색했을 때 나오는 '나'를 관리"],
  ], { h: 2.6 });
  takeaway(s, "마케팅하는 사람이 자신을 마케팅하지 못하면, 누가 믿겠는가");

  // =================== 05 실전 프로세스 ===================
  sectionSlide("05", "영업 실전 프로세스", "만남부터 재계약까지", "[추가 제안 파트] 강사님의 실제 영업 방식으로 보완 예정.");

  s = content("영업의 5단계",
    "[추가 제안 내용 — 강사님 실제 방식으로 보완 필요] 처음 시작하는 분들을 위해 영업의 흐름을 5단계로 정리했습니다. 가장 중요한 단계는 2번 '경청'과 3번 '진단'입니다. 제안은 대표님의 고민을 충분히 들은 다음에 합니다.");
  await flow(s, [
    ["준비", "매장 검색, 업종 공부, 자료 준비"],
    ["만남·경청", "말하기보다 듣기 7 : 3"],
    ["진단", "지금 무엇이 문제인지 함께 정리"],
    ["제안", "그 매장에 맞는 방법과 예상 결과"],
    ["계약·관리", "성과 보고, 그리고 재계약"],
  ]);
  takeaway(s, "제안은 맨 마지막 — 충분히 들은 사람만 제대로 제안할 수 있다");

  s = content("대표님의 마음을 여는 질문",
    "[추가 제안 내용] 첫 만남에서 바로 상품을 설명하지 말고, 이런 질문으로 대표님의 고민을 들으세요. 대표님이 말을 많이 할수록 계약 가능성은 높아집니다.");
  const qs = ["요즘 매출에서 가장 고민되시는 부분이 어떤 건가요?", "손님들은 주로 어떻게 알고 찾아오세요?",
    "예전에 마케팅을 해 보셨다면, 어떤 점이 아쉬우셨어요?", "6개월 뒤에 매장이 어떻게 되어 있으면 좋겠습니까?",
    "경쟁하는 근처 매장과 비교하면 우리 매장의 강점은 뭘까요?"];
  for (let i = 0; i < qs.length; i++) {
    const y = 1.3 + i * 0.68;
    await circleIcon(s, "FaQuestion", 0.6, y + 0.04, 0.48, i % 2 ? C.accent3 : C.accent1);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 1.25, y, w: 8.15, h: 0.56, fill: { color: C.background2 }, rectRadius: 0.08, objectName: "q" + i });
    s.addText(qs[i], { ...T, x: 1.45, y, w: 7.8, h: 0.56, fontSize: 15, color: C.text2, valign: "middle" });
  }

  s = content("거절은 '아직'이라는 뜻이다",
    "[추가 제안 내용 — 강사님 경험담 추가 권장] 거절은 끝이 아닙니다. 대부분은 '지금은 아니다' 또는 '아직 당신을 잘 모른다'는 뜻입니다. 거절당해도 관계를 남기면, 몇 달 뒤 먼저 연락이 옵니다.");
  compare(s, ["흔한 거절", ["\"지금은 여유가 없어요.\"", "\"다른 데랑 하고 있어요.\"", "\"생각 좀 해 볼게요.\"", "\"마케팅 해 봤는데 효과 없던데요.\""]],
    ["이렇게 받는다", ["\"매장 진단만 먼저 무료로 해 드릴까요?\"", "\"비교해 보실 자료만 드리겠습니다.\"", "\"어떤 부분이 고민되시는지 여쭤봐도 될까요?\"", "\"그때 무엇이 아쉬우셨는지 듣고 싶습니다.\""]]);
  takeaway(s, "거절당해도 관계는 남겨라 — 다음 기회는 그 관계에서 온다");

  s = content("계약은 끝이 아니라 시작이다",
    "제가 매출을 계속 낼 수 있는 이유는 새 계약보다 저를 믿고 계속 유지해 주시는 대표님들 덕분입니다. 신규 고객을 찾는 것보다 기존 고객을 지키는 게 훨씬 쉽고, 만족한 고객은 다른 대표님을 소개해 줍니다. [보완 필요: 강사님이 고객 관리에서 실제로 하시는 일]");
  await flow(s, [
    ["약속한 결과", "계약 때 약속한 것을 반드시 지킨다"],
    ["정기 보고", "숫자로 된 성과를 먼저 보고한다"],
    ["먼저 연락", "문제가 생기기 전에 먼저 챙긴다"],
    ["재계약·소개", "만족은 유지와 소개로 돌아온다"],
  ]);
  takeaway(s, "유지되는 고객이 쌓이면, 매출은 '더하기'가 아니라 '쌓기'가 된다");

  s = content("영업인의 하루",
    "[보완 필요: 강사님의 실제 하루 일과로 교체해 주세요] 아래는 예시입니다. 하루 12~15시간을 어떻게 쓰는지 보여 주면, 처음 시작하는 분들이 가장 현실적으로 배울 수 있는 부분입니다.");
  const day = [["오전 7시", "조찬 모임 (BNI 등)", "FaCoffee"], ["오전", "고객 성과 확인·보고", "FaChartLine"], ["오후", "대표님 미팅 2~3건", "FaHandshake"],
    ["저녁", "최고위과정·모임", "FaUsers"], ["밤", "공부·자료 준비·SNS", "FaBookOpen"]];
  for (let i = 0; i < 5; i++) {
    const x = 0.6 + i * 1.8;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.4, w: 1.6, h: 2.8, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "day" + i });
    await circleIcon(s, day[i][2], x + 0.5, 1.6, 0.6, i === 2 ? C.accent2 : C.accent1);
    s.addText(day[i][0], { ...T, x, y: 2.4, w: 1.6, h: 0.4, fontSize: 16, bold: true, color: C.text2, align: "center" });
    s.addText(day[i][1], { ...T, x: x + 0.12, y: 2.85, w: 1.36, h: 1.1, fontSize: 13, color: C.text1, align: "center", valign: "top" });
  }
  takeaway(s, "눈 떠서 잠들 때까지 — 힘들어서가 아니라 재미있어서", 4.45);

  s = content("영업인이 지켜야 할 약속",
    "[추가 제안 내용] 영업은 결국 신뢰의 일입니다. 당장 계약을 위해 지키지 못할 약속을 하면, 한 번은 팔아도 두 번은 못 팝니다. 특히 소개로 이어지는 영업에서는 한 번의 거짓말이 소개해 준 분의 신뢰까지 무너뜨립니다.");
  await cards(s, [
    ["FaBan", "과장하지 않는다", "\"무조건 1등\" 같은 약속은 하지 않는다"],
    ["FaClock", "시간을 지킨다", "미팅·보고·답변 시간은 반드시"],
    ["FaBalanceScale", "고객 편에 선다", "필요 없는 상품은 권하지 않는다"],
    ["FaShieldAlt", "소개자를 지킨다", "소개해 준 분의 얼굴에 먹칠하지 않는다"],
  ], { cols: 2, h: 2.9, y: 1.3 });
  takeaway(s, "한 번 팔고 끝낼 사람인가, 10년 갈 파트너인가", 4.5);

  // =================== 마무리 ===================
  section = "마무리";
  pres.addSection({ title: section });
  s = content("오늘의 핵심 5가지", "오늘 내용을 다섯 문장으로 정리합니다. 이 다섯 가지만 기억하셔도 충분합니다.");
  const keys = ["영업은 하는 만큼 돌아오는 일 — 최고의 보상은 성취감", "마케팅은 좋은 상품을 '알려서' 팔리게 돕는 일",
    "고객은 상품이 아니라 사람을 산다 — 첫인상·자신감·전문성", "찾아가는 영업에서 찾아오게 하는 영업으로 — 모임과 소개",
    "계약은 시작 — 약속을 지키면 유지와 소개로 돌아온다"];
  keys.forEach((k, i) => {
    const y = 1.3 + i * 0.7;
    s.addText(String(i + 1), { ...T, x: 0.6, y, w: 0.55, h: 0.55, fontSize: 26, bold: true, color: C.accent1, valign: "middle" });
    s.addText(k, { ...T, x: 1.25, y, w: 8.15, h: 0.55, fontSize: 17, bold: i === 0, color: C.text2, valign: "middle" });
  });

  s = content("이번 주 실천 과제", "교육이 끝나고 바로 실천할 수 있는 과제입니다. 다음 교육에서 결과를 함께 나눕니다. [보완 필요: 후속 교육/코칭 계획이 있다면 알려 주세요]");
  const todo = [["FaUserTie", "옷장 점검", "미팅용 단정한 옷 한 벌 준비하기"], ["FaPen", "30초 자기소개", "써 보고, 가족·동료 앞에서 말해 보기"],
    ["FaBook", "상품 Q&A 20개", "예상 질문 20개와 답을 노트에 정리"], ["FaUsers", "모임 하나 참석", "대표님들이 모이는 모임 한 곳 찾아가기"],
    ["FaSearch", "매장 하나 분석", "아는 매장 한 곳을 검색해 개선점 3가지 찾기"], ["FaHeart", "한 사람 돕기", "대가 없이 누군가를 한 명 소개·연결하기"]];
  await cards(s, todo, { cols: 3, h: 3.0, y: 1.35, accent: C.accent2 });

  s = pres.addSlide({ masterName: "COVER", sectionTitle: section });
  s.addText("하는 만큼 성취하는 일,", { placeholder: "title" });
  s.addText("영업에 오신 것을 환영합니다", { ...T, x: 0.6, y: 2.25, w: 8.8, h: 0.8, fontSize: 36, bold: true, color: C.accent1 });
  s.addText("질문과 나눔", { ...T, x: 0.6, y: 3.6, w: 8.8, h: 0.5, fontSize: 20, bold: true, color: C.background1 });
  s.addText("강사  OOO 대표  |  연락처·SNS (보완 필요)", { ...T, x: 0.6, y: 4.5, w: 8.8, h: 0.4, fontSize: 14, color: "C9D1DC" });
  s.addNotes("마무리: '저는 20년 동안 성취감 없이 살았습니다. 지금은 아침에 눈 뜨는 게 행복합니다. 여러분도 그 기쁨을 느끼셨으면 좋겠습니다.' 이후 질의응답.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
