// 영업의 본질 - 마케팅 영업 기초 교육 자료 (1교시·2교시, 각 60분)
// 실행: NODE_PATH=<pptxgenjs가 설치된 node_modules> node build_sales_deck.js [출력파일]
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.PPTX_APPLY_THEME ||
  "/root/.claude/skills/synced/1a62ff30-a17b-4a9d-bb46-a287bcb80359_f6686bbd-ce69-4d88-ac53-ac3e093346d8/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "영업의_본질_교육자료.pptx";
const SPEAKER_PHOTO = path.join(__dirname, "..", "cbmc", "speaker.jpg");
const IMG = (f) => path.join(__dirname, "img", f);
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
const SOFT_ORANGE = "FFF1EA", SOFT_GREEN = "E8F7EF", MUTED_ON_DARK = "C9D1DC";
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
  pres.author = "이인선";
  const C = pres.SchemeColor;
  const T = { isTextBox: true, margin: 0 };

  pres.defineSlideMaster({
    title: "COVER", background: { color: HEX.dk2 },
    objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.5, w: 8.8, h: 1.0, fontSize: 44, bold: true, color: C.background1, align: "left", valign: "top", margin: 0 }, text: "" } }],
  });
  pres.defineSlideMaster({
    title: "SECTION", background: { color: HEX.dk2 },
    objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.3, w: 8.8, h: 1.0, fontSize: 38, bold: true, color: C.background1, align: "left", valign: "middle", margin: 0 }, text: "" } }],
  });
  pres.defineSlideMaster({
    title: "CONTENT", background: { color: HEX.lt1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 8.8, h: 0.7, fontSize: 28, bold: true, color: C.text2, align: "left", valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "영업의 본질  |  (주)상생어벤져스 이인선", options: { x: 0.6, y: 5.22, w: 5, h: 0.25, fontSize: 10, color: C.accent6, margin: 0 } } },
    ],
    slideNumber: { x: 9.0, y: 5.22, w: 0.4, h: 0.25, fontSize: 10, color: C.accent6, align: "right" },
  });

  let section = "";
  const boltIcon = await icon("FaBolt", HEX.accent1);
  const content = (title, notes) => {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
    s.addText(title, { placeholder: "title" });
    if (notes) s.addNotes(notes);
    return s;
  };
  const takeaway = (s, text, y = 4.55) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 8.8, h: 0.5, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "takeawayBox" });
    s.addImage({ data: boltIcon, x: 0.78, y: y + 0.13, w: 0.24, h: 0.24, altText: "핵심" });
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
      if (rh < 1.5) {
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
    [[L, C.accent6, C.background2], [R, C.accent1, SOFT_ORANGE]].forEach(([[head, items], color, fill], i) => {
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
      s.addText(steps[i][0], { ...T, x: x + 0.2, y: y + 0.9, w: w - 0.35, h: 0.45, fontSize: n > 4 ? 15 : 16, bold: true, color: C.text2 });
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
    s.addText(subtitle, { ...T, x: 0.6, y: 3.35, w: 8.8, h: 0.5, fontSize: 18, color: MUTED_ON_DARK });
    if (notes) s.addNotes(notes);
    return s;
  };
  const sessionSlide = (label, title, parts, notes) => {
    section = label;
    pres.addSection({ title: label });
    const s = pres.addSlide({ masterName: "SECTION", sectionTitle: label });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.0, w: 2.6, h: 0.55, fill: { color: C.accent1 }, rectRadius: 0.27, objectName: "sessionTag" });
    s.addText(label + " · 60분", { ...T, x: 0.6, y: 1.0, w: 2.6, h: 0.55, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
    s.addText(title, { ...T, x: 0.6, y: 1.8, w: 8.8, h: 0.9, fontSize: 38, bold: true, color: C.background1, valign: "middle" });
    s.addText(parts, { ...T, x: 0.6, y: 3.05, w: 8.8, h: 1.2, fontSize: 17, color: MUTED_ON_DARK, valign: "top", paraSpaceAfter: 6 });
    if (notes) s.addNotes(notes);
  };
  // 실습 슬라이드: 초록 배지 + 단계 + 결과물
  const practice = async (title, minutes, steps, output, notes) => {
    const s = content(title, notes);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.6, y: 0.45, w: 1.8, h: 0.5, fill: { color: C.accent2 }, rectRadius: 0.25, objectName: "practiceBadge" });
    s.addText("실습 · " + minutes + "분", { ...T, x: 7.6, y: 0.45, w: 1.8, h: 0.5, fontSize: 15, bold: true, color: C.background1, align: "center", valign: "middle" });
    steps.forEach((st, i) => {
      const y = 1.3 + i * 0.68;
      s.addShape(pres.shapes.OVAL, { x: 0.6, y: y + 0.04, w: 0.48, h: 0.48, fill: { color: C.accent2 }, objectName: "pStep" + i });
      s.addText(String(i + 1), { ...T, x: 0.6, y: y + 0.04, w: 0.48, h: 0.48, fontSize: 17, bold: true, color: C.background1, align: "center", valign: "middle" });
      s.addText(st, { ...T, x: 1.3, y, w: 8.1, h: 0.56, fontSize: 16, color: C.text2, valign: "middle" });
    });
    const oy = 1.3 + steps.length * 0.68 + 0.15;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: oy, w: 8.8, h: 0.6, fill: { color: SOFT_GREEN }, rectRadius: 0.1, objectName: "practiceOutput" });
    s.addText([{ text: "결과물  ", options: { bold: true, color: C.accent2 } }, { text: output, options: { color: C.text2 } }],
      { ...T, x: 0.9, y: oy, w: 8.3, h: 0.6, fontSize: 15, valign: "middle" });
    return s;
  };

  // =================== 오프닝 ===================
  section = "오프닝";
  pres.addSection({ title: section });
  let s = pres.addSlide({ masterName: "COVER", sectionTitle: section });
  s.addText("마케팅 영업 기초 교육", { ...T, x: 0.6, y: 0.8, w: 6, h: 0.45, fontSize: 18, bold: true, color: C.accent1 });
  s.addText("영업의 본질", { placeholder: "title" });
  s.addText("하는 만큼 성취하는 일 — 상품이 아니라 '나'를 믿게 만드는 법", { ...T, x: 0.6, y: 2.55, w: 8.8, h: 0.5, fontSize: 20, color: MUTED_ON_DARK });
  s.addText([
    { text: "이인선 상무이사", options: { bold: true, fontSize: 18, color: C.background1, breakLine: true } },
    { text: "(주)상생어벤져스컴퍼니  ·  (주)먹스타 대표이사", options: { fontSize: 14, color: MUTED_ON_DARK } },
  ], { ...T, x: 0.6, y: 4.1, w: 8.8, h: 0.8 });
  s.addNotes("인사 후 시작. '오늘은 상품을 파는 기술이 아니라, 영업이라는 일의 본질을 이야기하려고 합니다. 1교시는 마음가짐, 2교시는 실전입니다.'");

  s = content("강사 소개", "간단히 소개합니다. 군 생활 이야기는 바로 다음 파트에서 자세히 합니다. (약 2분)");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.25, w: 2.9, h: 3.7, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "photoCard" });
  s.addImage({ path: SPEAKER_PHOTO, x: 0.75, y: 1.4, w: 2.6, h: 2.92, altText: "이인선 강사 사진", objectName: "speakerPhoto" });
  s.addText("이인선 상무이사", { ...T, x: 0.75, y: 4.4, w: 2.6, h: 0.45, fontSize: 18, bold: true, color: C.text2, align: "center", valign: "middle" });
  s.addText([
    { text: "(주)상생어벤져스컴퍼니 상무이사  ·  (주)먹스타 대표이사", options: { breakLine: true } },
    { text: "크리에이터 「먹스타선장 맛고양」" },
  ], { ...T, x: 3.9, y: 1.25, w: 5.5, h: 0.65, fontSize: 14, bold: true, color: C.accent1, valign: "top" });
  const stats0 = [["약 20년", "육군 부사관\n군 생활"], ["40개", "군 복무 중\n취득 자격증"], ["2.5억+", "숏폼 누적\n조회수"], ["1년", "창업 후\nM&A까지"]];
  for (let i = 0; i < 4; i++) {
    const x = 3.9 + i * 1.4;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.05, w: 1.28, h: 1.3, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "statCard" + i });
    s.addText(stats0[i][0], { ...T, x, y: 2.15, w: 1.28, h: 0.5, fontSize: 20, bold: true, color: i === 2 ? C.accent1 : C.text2, align: "center", valign: "middle" });
    s.addText(stats0[i][1], { ...T, x, y: 2.65, w: 1.28, h: 0.6, fontSize: 11, color: C.text1, align: "center", valign: "top" });
  }
  s.addText([
    { text: "중앙대학교 · 소상공인진흥공단 · SBA경제진흥원 숏폼 강사", options: { bullet: true, breakLine: true } },
    { text: "강남외식산업 총동문회 사무차장 (요식업 대표 300명)", options: { bullet: true, breakLine: true } },
    { text: "직영 매장 운영: 중화객잔수 · 미친양꼬치 · 케이찹사라다", options: { bullet: true, breakLine: true } },
    { text: "CADO 40기 · BNI · CBMC 활동", options: { bullet: true } },
  ], { ...T, x: 3.9, y: 3.55, w: 5.5, h: 1.45, fontSize: 13, color: C.text1, valign: "top", paraSpaceAfter: 5 });

  s = content("오늘의 구성: 1시간 × 2번", "1교시는 '왜, 무엇을' — 영업의 마음가짐. 2교시는 '어떻게' — 실전과 실습. 실습이 3번 있으니 펜과 종이를 준비해 달라고 안내합니다.");
  [["1교시 · 영업의 마음가짐", ["01  왜 영업인가 — 20년 군 생활에서 영업으로", "02  마케팅·영업의 본질", "03  신뢰를 만드는 3가지", "실습 ①  나는 왜 영업을 하는가"], C.accent1, SOFT_ORANGE],
   ["2교시 · 영업의 실전", ["04  찾아오게 만드는 영업 — 모임과 소개", "05  첫 만남부터 재계약까지", "06  먹스타와 함께하는 영업", "실습 ②③  원투원 미팅 · 매장 사전 조사"], C.accent2, SOFT_GREEN]
  ].forEach(([head, items, color, fill], i) => {
    const x = 0.6 + i * 4.55;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 4.25, h: 3.6, fill: { color: fill }, rectRadius: 0.12, objectName: "session" + i });
    s.addText(head, { ...T, x: x + 0.3, y: 1.5, w: 3.7, h: 0.5, fontSize: 19, bold: true, color });
    items.forEach((t, j) => {
      s.addText(t, { ...T, x: x + 0.3, y: 2.2 + j * 0.62, w: 3.7, h: 0.5, fontSize: 14, bold: j === 3, color: j === 3 ? color : C.text2, valign: "middle" });
    });
  });

  // =================== 1교시 ===================
  sessionSlide("1교시", "영업의 마음가짐", "01  왜 영업인가\n02  마케팅·영업의 본질\n03  신뢰를 만드는 3가지", "1교시 60분. 01파트 15분, 실습① 5분, 02파트 15분, 03파트 20분, 정리 5분.");

  sectionSlide("01", "왜 영업인가", "안정의 20년, 그리고 성취의 시작", "강사 본인의 이야기로 공감대를 만드는 파트입니다. (15분)");

  s = content("나의 첫 직업: 육군 부사관 약 20년",
    "저는 약 20년 동안 육군 부사관으로 근무했습니다. 대충 산 게 아닙니다. 표창도 받았고, 대체불가부사관에 선정되기도 했습니다. 2014년에는 미8군 와이트먼 부사관학교(Wightman NCO Academy)의 Warrior Leader Course를 수료했습니다. 미군들과 함께 교육받으면서 더 넓은 세상을 봤습니다. 거기서 조직 관리와 시스템, 그리고 끝까지 해내는 실행력을 익혔습니다.");
  const army = [["army_award.jpg", 652, 444, "표창 수상 · 대체불가부사관 선정"], ["army_usfk.jpg", 654, 444, "미군 부사관학교 교육 동기들과"], ["nco_academy_diploma.jpg", 511, 674, "미8군 부사관학교 수료 (2014)"]];
  { const H = 2.3, y = 1.35; let x = 0.6;
    const ws = army.map(([, w, h]) => H * w / h), gap = (8.8 - ws.reduce((a, b) => a + b, 0)) / 2;
    for (let i = 0; i < 3; i++) {
      s.addImage({ path: IMG(army[i][0]), x, y, w: ws[i], h: H, altText: army[i][3], objectName: "armyPhoto" + i });
      s.addText(army[i][3], { ...T, x, y: y + H + 0.08, w: ws[i], h: 0.4, fontSize: 12, color: C.text1, align: "center" });
      x += ws[i] + gap;
    } }
  takeaway(s, "군에서 배운 것: 조직 관리, 시스템, 그리고 끝까지 해내는 실행력", 4.55);

  s = content("쉬지 않고 공부했다: 자격증 40개",
    "군 생활 중에 행정사, 산업안전기사를 비롯해 자격증을 40개 땄습니다. 시간이 남아서가 아니라, 쉬지 않고 공부했기 때문입니다. 영업도 똑같습니다. 공부한 만큼 대표님 앞에서 막힘이 없습니다. 이 습관이 지금 영업의 바탕이 됐습니다.");
  s.addImage({ path: IMG("certificates_40.jpg"), x: 0.6, y: 1.2, w: 3.2 * 450 / 591, h: 3.2, altText: "자격증 40개 모음 사진", objectName: "certPhoto" });
  s.addText("40개", { ...T, x: 4.0, y: 1.3, w: 5.4, h: 1.0, fontSize: 60, bold: true, color: C.accent1, valign: "middle" });
  s.addText("군 복무 중 취득한 자격증", { ...T, x: 4.0, y: 2.3, w: 5.4, h: 0.45, fontSize: 18, bold: true, color: C.text2 });
  s.addText([
    { text: "행정사 · 산업안전기사 등 국가자격", options: { bullet: true, breakLine: true } },
    { text: "근무가 끝난 시간에 꾸준히 공부한 결과", options: { bullet: true, breakLine: true } },
    { text: "영업에서도 같다: 공부한 만큼 막힘이 없다", options: { bullet: true } },
  ], { ...T, x: 4.0, y: 2.95, w: 5.4, h: 1.4, fontSize: 15, color: C.text1, valign: "top", paraSpaceAfter: 6 });
  takeaway(s, "꾸준함은 배신하지 않는다 — 군에서 만든 공부 습관이 영업의 무기가 됐다", 4.55);

  s = content("20년 군 생활이 내게 준 것과 주지 않은 것",
    "1년 뒤, 5년 뒤 월급이 얼마인지 알 수 있는 안정감은 있었습니다. 전역 전 마지막 연봉도 6,200만 원 정도로 적지 않았습니다. 그런데 '내가 이걸 해서 이런 성과를 냈다'는 성취감은 하나도 없었습니다. 요즘 사람들은 직업을 고를 때 꿈과 미래를 봅니다. 월급만으로는 몇십억 하는 서울 아파트는 절대 살 수 없겠다는 생각도 들었습니다.");
  compare(s, ["군 생활 20년이 준 것", ["따박따박 들어오는 월급", "1년 뒤, 5년 뒤가 예측되는 안정감", "마지막 연봉 약 6,200만 원 — 생활과 저축 가능", "평생 받는 군인연금"]],
    ["주지 않은 것", ["내가 한 일에 대한 성과와 성취감", "꿈과 미래에 대한 기대", "월급만으로는 닿을 수 없는 목표 (서울 아파트)"]]);
  takeaway(s, "안정은 있었지만, '내가 해냈다'는 느낌은 없었다");

  s = content("39살부터 매달 연금이 나오는데, 왜 영업을?",
    "저는 20년 군 생활을 해서 39살부터 매달 약 180만 원씩 군인연금을 받고 있습니다. 많은 분들이 물어보십니다. '연금 나오는데 그냥 편하게 살지, 왜 이렇게 힘들게 일해요?' 제 답은 이렇습니다. 연금은 생활을 지켜 줍니다. 하지만 성취감은 주지 못합니다. 그리고 좋은 제품과 서비스가 있는데도 홍보를 못 해서 사라지는 가게들을 너무 많이 봤습니다. 그분들을 돕는 일이 하고 싶었습니다.");
  s.addImage({ path: IMG("pension_sms.jpg"), x: 0.6, y: 1.2, w: 1.65, h: 1.65 * 685 / 347, altText: "매달 연금 입금 문자", objectName: "pensionSms" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 2.5, y: 1.3, w: 3.3, h: 3.0, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "pensionCard" });
  await circleIcon(s, "FaShieldAlt", 2.75, 1.5, 0.6, C.accent6);
  s.addText("매달 약 180만 원", { ...T, x: 2.75, y: 2.25, w: 2.9, h: 0.5, fontSize: 21, bold: true, color: C.text2 });
  s.addText("39살부터 평생 받는 군인연금.\n이미 '안정'은 확보되어 있었다.\n편하게 살 수 있는 선택지가 있었다.", { ...T, x: 2.75, y: 2.8, w: 2.9, h: 1.4, fontSize: 14, color: C.text1, valign: "top" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.05, y: 1.3, w: 3.35, h: 3.0, fill: { color: SOFT_ORANGE }, rectRadius: 0.12, objectName: "choiceCard" });
  await circleIcon(s, "FaFire", 6.3, 1.5, 0.6, C.accent1);
  s.addText("그래도 성취를 택했다", { ...T, x: 6.3, y: 2.25, w: 3.0, h: 0.5, fontSize: 20, bold: true, color: C.accent1 });
  s.addText("좋은 상품이 있는데도 홍보를 못 해 사라지는 가게들을 돕고 싶었다.", { ...T, x: 6.3, y: 2.8, w: 2.95, h: 1.4, fontSize: 14, color: C.text1, valign: "top" });
  takeaway(s, "영업은 돈 때문에만 하는 일이 아니다 — '내가 해냈다'를 느끼는 일", 4.6);

  s = content("실패도 있었다: 전업투자로 번 8억을 다 잃다",
    "솔직하게 말씀드리겠습니다. 저는 전업투자를 2년 했습니다. 한때 8억까지 벌었지만, 다 날렸습니다. 블로그에 투자 기록만 267편을 남길 만큼 열심히 했지만, 시장은 제가 통제할 수 있는 게 아니었습니다. 그때 깨달았습니다. 운과 시장에 맡기는 돈은 언제든 사라질 수 있다. 하지만 내가 사람을 만나고 신뢰를 쌓아서 버는 돈은 내가 만든 것이고, 쌓인다. 그래서 저는 영업을 합니다.");
  s.addImage({ path: IMG("invest_stock.jpg"), x: 0.6, y: 1.2, w: 1.6, h: 1.6 * 756 / 382, altText: "투자 손실 화면 (계좌 정보 가림)", objectName: "stockShot" });
  s.addImage({ path: IMG("invest_blog.jpg"), x: 2.35, y: 1.2, w: 1.6, h: 1.6 * 756 / 400, altText: "블로그 투자 기록 카테고리", objectName: "blogShot" });
  [["시장에 맡긴 돈", "8억까지 벌었지만 다 잃었다 · 내가 통제할 수 없다 · 쌓이지 않는다", C.accent6, C.background2],
   ["내가 만드는 돈 (영업)", "하는 만큼 돌아온다 · 신뢰는 내가 통제한다 · 고객과 소개가 쌓인다", C.accent1, SOFT_ORANGE]].forEach(([h, d, col, fill], i) => {
    const y = 1.2 + i * 1.6;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.5, y, w: 4.9, h: 1.4, fill: { color: fill }, rectRadius: 0.12, objectName: "moneyCard" + i });
    s.addText(h, { ...T, x: 4.8, y: y + 0.15, w: 4.4, h: 0.45, fontSize: 18, bold: true, color: col });
    s.addText(d, { ...T, x: 4.8, y: y + 0.65, w: 4.4, h: 0.65, fontSize: 14, color: C.text1, valign: "top" });
  });
  takeaway(s, "운에 맡긴 돈은 사라졌고, 신뢰로 번 돈은 쌓였다", 4.55);

  s = content("숫자로 보는 변화",
    "전역하기 전 마지막 연봉이 약 6,200만 원이었습니다. 지금은 한 달에 약 8천만 원의 매출을 내고 있습니다. 1년 동안 벌던 것보다 많은 금액을 한 달에, 저를 믿고 대표님들이 맡겨 주고 계신 겁니다. 그리고 창업 1년 만에 회사 가치를 인정받아 M&A까지 했습니다. 자랑이 아니라, 저를 믿고 계속 유지해 주시는 대표님들 덕분입니다.");
  const stats = [["6,200만 원", "전역 전 마지막 '연봉'", C.accent6], ["약 8천만 원", "지금의 '월' 매출", C.accent1], ["80~90%", "만남 대비 계약률", C.accent2]];
  stats.forEach(([n, l, col], i) => {
    const x = 0.6 + i * 3.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.45, w: 2.8, h: 2.3, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "stat" + i });
    s.addText(n, { ...T, x, y: 1.75, w: 2.8, h: 0.9, fontSize: 30, bold: true, color: col, align: "center", valign: "middle" });
    s.addText(l, { ...T, x, y: 2.75, w: 2.8, h: 0.5, fontSize: 16, color: C.text1, align: "center" });
  });
  takeaway(s, "1년 연봉보다 많은 매출을 한 달에 — 그리고 창업 1년 만에 M&A", 4.2);

  s = content("신뢰가 쌓이면 계약의 크기가 달라진다",
    "처음에는 동네 식당 한 곳부터 시작했습니다. 결과로 신뢰가 쌓이니까 점점 금액이 큰 계약이 생겼습니다. 깡우동과 1억 2천만 원, 코이라멘과 1억 2천만 원 연간 계약을 했고, 제주맥주와는 먹스타파티 5천만 원 계약을 했습니다. 작은 계약을 제대로 해낸 것이 큰 계약으로 돌아왔습니다.");
  const big = [["깡우동", "1억 2천만 원", "1년 계약 · 월 1,000만 원", "숏폼 영상 제작(월 8회) + SNS 채널 관리", "FaUtensils"],
    ["코이라멘", "1억 2천만 원", "1년 계약 · 월 1,000만 원", "숏폼 영상 제작(월 8회) + SNS 채널 관리", "FaUtensils"],
    ["제주맥주", "5천만 원", "먹스타파티 총 5회", "회당 숏폼 영상 30~50개 제작", "FaGlassCheers"]];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 3.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 2.8, h: 2.95, fill: { color: i === 2 ? SOFT_ORANGE : C.background2 }, rectRadius: 0.12, objectName: "bigDeal" + i });
    await circleIcon(s, big[i][4], x + 0.25, 1.5, 0.6, C.accent1);
    s.addText(big[i][0], { ...T, x: x + 1.0, y: 1.5, w: 1.7, h: 0.6, fontSize: 19, bold: true, color: C.text2, valign: "middle" });
    s.addText(big[i][1], { ...T, x: x + 0.2, y: 2.25, w: 2.5, h: 0.65, fontSize: 24, bold: true, color: C.accent1, valign: "middle" });
    s.addText(big[i][2], { ...T, x: x + 0.25, y: 2.95, w: 2.4, h: 0.4, fontSize: 14, bold: true, color: C.text2 });
    s.addText(big[i][3], { ...T, x: x + 0.25, y: 3.35, w: 2.4, h: 0.8, fontSize: 13, color: C.text1, valign: "top" });
  }
  takeaway(s, "작은 계약을 제대로 해내면, 다음 계약의 단위가 바뀐다", 4.5);

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
    "월급은 정해져 있습니다. 영업은 바닥도 천장도 없습니다. 무섭기도 하지만, 그래서 기회입니다. 처음엔 바닥을 경험할 수 있습니다. 그 시기를 버티는 사람이 천장을 봅니다.");
  compare(s, ["월급 구조", ["일한 만큼이 아니라 '정해진 만큼'", "1년 뒤, 5년 뒤 금액이 예측됨", "성과를 내도 보상은 비슷함"]],
    ["영업 구조", ["안 하면 월 100만 원도 어렵다", "하면 월 1,000만~2,000만 원도 가능", "결과가 곧 나의 평가 — 성취감"]]);
  takeaway(s, "영업은 '시간 × 노력 × 신뢰'가 그대로 수입이 되는 일");

  await practice("실습 ① 나는 왜 영업을 하려는가", 5, [
    "종이에 '내가 영업을 하려는 이유'를 3줄로 적는다",
    "1년 뒤 이루고 싶은 목표를 숫자로 하나 적는다 (예: 월 계약 10건)",
    "옆 사람과 1분씩 서로 이야기해 준다",
  ], "나만의 '영업 이유' 3줄 + 1년 목표 숫자 1개",
    "강사님의 이유('성취감', '사라지는 가게를 돕고 싶다')를 먼저 예시로 말해 주고 시작합니다. 힘들 때 다시 꺼내 볼 문장이 된다고 안내합니다.");

  // =================== 02 본질 ===================
  sectionSlide("02", "마케팅·영업의 본질", "좋은 상품이 안 팔리는 이유", "마케팅과 영업이 무엇인지 정의하는 파트. (15분)");

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
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.05, h: 1.35, fill: { color: i === 7 ? SOFT_ORANGE : C.background2 }, rectRadius: 0.1, objectName: "ind" + i });
    s.addImage({ data: await icon(inds[i][0], i === 7 ? HEX.accent1 : HEX.dk2), x: x + 0.78, y: y + 0.2, w: 0.5, h: 0.5, altText: inds[i][1] });
    s.addText(inds[i][1], { ...T, x, y: y + 0.82, w: 2.05, h: 0.4, fontSize: 15, bold: true, color: i === 7 ? C.accent1 : C.text2, align: "center" });
  }
  takeaway(s, "모든 사장님은 잠재 고객 — 업종보다 '알리는 일'이 공통분모", 4.55);

  s = content("\"우리 상품은 최고\"인데 왜 안 팔릴까?",
    "대표님들은 '내 상품은 어디 가도 최고야'라고 생각하십니다. 실제로 좋은 상품도 많습니다. 그런데 그 안에만 갇혀 있는 분들이 너무 많습니다. 좋은 제품과 서비스가 있는데도 홍보를 못 해서 사라지는 가게들을 저는 너무 많이 봤습니다. 아무리 좋아도 모르면 못 삽니다. 그걸 알려 주는 게 진짜, 찐입니다.");
  compare(s, ["갇혀 있는 상품", ["품질은 자신 있다", "그런데 아는 사람이 없다", "기다리면 손님이 올 거라 믿는다", "결과: 좋은데 사라진다"]],
    ["알려진 상품", ["품질에 '알림'이 더해진다", "필요한 사람에게 닿는다", "고객이 먼저 찾아온다", "결과: 좋아서 팔린다"]]);
  takeaway(s, "좋은 상품을 많은 사람에게 알려 팔리게 돕는 것 — 그것이 우리의 일");

  s = content("우리가 하는 일: 사람을 살리는 마케팅",
    "처음에는 식당 사장님들 홍보를 도와드리는 수준이었습니다. 하다 보니 마케팅은 광고가 아니라 '매출을 만드는 구조'라는 걸 깨달았습니다. 이 일을 하면서 가장 보람찬 순간은 '이 대표님 덕분에 가게가 다시 살아났어요'라는 말을 들을 때입니다. 여주 엄마네 사장님은 손님이 너무 많이 와서 '마케팅 좀 살살 해 달라'고 하셨습니다.");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.3, w: 8.8, h: 1.45, fill: { color: SOFT_ORANGE }, rectRadius: 0.12, objectName: "quote1" });
  s.addImage({ data: await icon("FaQuoteLeft", HEX.accent1), x: 0.9, y: 1.5, w: 0.45, h: 0.45, altText: "인용" });
  s.addText("\"이 대표님 덕분에 가게가 다시 살아났어요\"", { ...T, x: 1.55, y: 1.4, w: 7.7, h: 0.75, fontSize: 24, bold: true, color: C.text2, valign: "middle" });
  s.addText("— 강사가 이 일에서 가장 보람을 느끼는 순간", { ...T, x: 1.55, y: 2.15, w: 7.7, h: 0.4, fontSize: 13, color: C.text1 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 2.95, w: 8.8, h: 1.35, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "quote2" });
  s.addImage({ data: await icon("FaQuoteLeft", HEX.accent2), x: 0.9, y: 3.15, w: 0.45, h: 0.45, altText: "인용" });
  s.addText("\"손님이 너무 많아요. 마케팅 좀 살살 해 주세요\"", { ...T, x: 1.55, y: 3.05, w: 7.7, h: 0.75, fontSize: 22, bold: true, color: C.text2, valign: "middle" });
  s.addText("— 여주 「엄마네」 사장님 (약 2년째 함께하는 중)", { ...T, x: 1.55, y: 3.8, w: 7.7, h: 0.4, fontSize: 13, color: C.text1 });
  takeaway(s, "마케팅은 광고가 아니라 매출을 만드는 구조 — 그들의 성공이 곧 나의 성공", 4.5);

  s = content("고객은 상품보다 '사람'을 산다",
    "마케팅 상품은 회사마다 비슷해 보입니다. 블로그, 숏폼, 광고… 대표님 입장에서는 누구에게 맡겨도 비슷해 보이죠. 그래서 결정은 결국 '이 사람을 믿을 수 있나'로 내려집니다. 영업의 본질은 상품 설명이 아니라 신뢰를 쌓는 일입니다.");
  await cards(s, [
    ["FaBoxOpen", "상품은 비슷하다", "마케팅 상품은 어느 회사나 비슷해 보인다"],
    ["FaUserCheck", "결정은 사람이 한다", "\"이 사람에게 맡기면 되겠다\"는 믿음"],
    ["FaHandshake", "영업 = 신뢰 쌓기", "말이 아니라 준비·태도·결과로 증명"],
  ], { h: 2.6 });
  takeaway(s, "우리가 파는 것은 상품이 아니라 '믿음'이다");

  s = content("판매원과 영업 파트너의 차이",
    "판매원은 내 상품을 설명하고, 파트너는 고객의 매출을 고민합니다. 고객은 판매원은 피하고, 파트너는 찾습니다. 제가 가장 자랑스럽게 생각하는 것도 '고객과의 약속을 성과로 지키는 것'입니다.");
  compare(s, ["판매원", ["내 상품 이야기부터 꺼낸다", "이번 달 내 실적이 목표", "계약하면 끝", "고객이 피한다"]],
    ["영업 파트너", ["대표님의 고민부터 듣는다", "대표님 매출이 오르는 것이 목표", "계약은 관계의 시작", "고객이 찾아온다"]]);
  takeaway(s, "고객의 매출을 내 일처럼 고민하는 사람이 결국 선택받는다");

  // =================== 03 신뢰 3요소 ===================
  sectionSlide("03", "신뢰를 만드는 3가지", "계약률 80~90%의 비밀", "강사의 계약률이 높은 이유를 구체적으로 풀어 주는 파트. (20분)");

  s = content("나는 먼저 찾아가지 않는다",
    "제 계약률이 80~90%인 이유는, 제가 먼저 찾아가거나 먼저 제안하는 경우가 거의 없기 때문입니다. 대표님들이 저를 찾아오게 만들었습니다. 찾아온 사람은 이미 절반은 마음을 정하고 온 사람입니다.");
  compare(s, ["찾아가는 영업 (Push)", ["내가 먼저 연락하고 설득한다", "상대는 경계부터 한다", "가격 비교 대상이 된다", "계약률이 낮다"]],
    ["찾아오게 하는 영업 (Pull)", ["상대가 먼저 묻고 요청한다", "이미 신뢰를 갖고 온다", "'누구에게'가 아니라 '언제' 맡길지 고민", "계약률 80~90%"]]);
  takeaway(s, "목표는 '설득'이 아니라 '찾아오게 만드는 것'");

  s = content("처음엔 찾아가야 한다 — 단, '우위'를 갖고",
    "처음 시작할 때는 아무도 나를 모릅니다. 저도 제대 후 처음엔 인스타그램으로 영업을 시작했습니다. 제 인스타그램을 본 사장님이 '우리 매장도 홍보해 달라'고 하신 게 첫 계약이었습니다. 찾아가더라도 상대보다 정보든 경험이든 겉으로 보이는 모습이든 '우세'가 있어야 합니다. 이 세 가지가 신뢰를 만듭니다.");
  await cards(s, [
    ["FaUserTie", "① 첫인상", "단정한 외모 — 보기만 해도 '맡겨도 되겠다'"],
    ["FaEye", "② 자신감", "눈을 보고, 결과를 약속하는 태도"],
    ["FaBookOpen", "③ 전문성", "어떤 질문에도 막힘없는 준비"],
  ], { h: 2.6 });
  takeaway(s, "강사의 첫 계약: 인스타그램을 본 사장님의 \"우리 매장도 해 주세요\"");

  s = content("① 첫인상: 단정함은 실력의 첫 증거",
    "보험·영업하는 분들이 왜 정장을 입고 다닐까 처음엔 몰랐습니다. 이제는 압니다. 청바지에 구겨진 티셔츠를 입고 영업을 왔다면? 겪어 봐야 알겠지만, 보기만 해도 '잘 모를 것 같고, 맡기면 제대로 안 해 줄 것 같은' 이미지가 듭니다. 꼭 정장일 필요는 없습니다. 단정하면 됩니다.");
  compare(s, ["이렇게는 NO", ["구겨진 티셔츠, 낡은 청바지", "정리 안 된 머리, 지저분한 신발", "휴대폰만 보며 앉아 있기", "명함 없이 말로만 소개"]],
    ["이렇게 YES", ["다림질된 셔츠·깔끔한 재킷 (정장 필수 아님)", "단정한 머리, 깨끗한 신발", "바른 자세, 밝은 인사", "명함·자료를 준비해 건네기"]]);
  takeaway(s, "첫인상은 3초, 그 3초가 '들어 줄지 말지'를 정한다");

  s = content("② 자신감: \"맡겨 주시면 매출을 올리겠습니다\"",
    "대표님을 만나면 눈을 잘 쳐다보고, '저에게 맡겨 주시면 제대로 매출을 끌어올리겠습니다'라는 자신감을 보여 주세요. 자신감은 큰소리가 아니라 준비에서 나옵니다. 아래 문장을 다 같이 소리 내어 연습해 봅시다.");
  await cards(s, [
    ["FaEye", "눈을 맞춘다", "말할 때도, 들을 때도 상대의 눈을 본다"],
    ["FaMicrophone", "말끝을 흐리지 않는다", "\"~인 것 같아요\" 대신 \"~입니다\""],
    ["FaBullseye", "결과로 말한다", "\"비슷한 매장에서 이렇게 올렸습니다\""],
  ], { y: 1.35, h: 2.3 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 3.9, w: 8.8, h: 1.1, fill: { color: SOFT_ORANGE }, rectRadius: 0.1, objectName: "practiceLine" });
  s.addText([
    { text: "다 같이 따라 해 보기", options: { fontSize: 13, bold: true, color: C.accent1, breakLine: true } },
    { text: "\"대표님, 이 부분은 제가 자신 있습니다. 맡겨 주시면 매주 결과로 보여 드리겠습니다.\"", options: { fontSize: 16, bold: true, color: C.text2 } },
  ], { ...T, x: 0.9, y: 3.9, w: 8.3, h: 1.1, valign: "middle" });

  s = content("③ 전문성: 사장님들은 이미 많이 안다",
    "요즘은 정보가 너무 많이 공개되어 있습니다. 마케팅 회사만 검색해도 수십, 수백 곳이 나오고, 사장님들은 가만히 있어도 전화가 엄청 옵니다. 저도 대표라 전화가 많이 오는데, '마케팅 회사인데요~' 하면 바로 끊습니다. 유튜브, 블로그에 정보도 넘칩니다. 그래서 우리가 전문가가 되지 않으면 신뢰가 생기지 않습니다. 대표님이 질문했는데 '그건 제가 모르는데요' 하면 그 순간 끝입니다.");
  await cards(s, [
    ["FaSearch", "검색하면 수백 곳", "마케팅 회사는 넘쳐난다 — 비교당하는 게 기본"],
    ["FaPhoneSlash", "하루에도 여러 통", "\"마케팅 회사인데요~\" 전화는 바로 끊긴다"],
    ["FaYoutube", "정보도 넘친다", "유튜브·블로그로 공부한 사장님이 많다"],
  ], { h: 2.6 });
  takeaway(s, "\"그건 제가 모르는데요\" — 이 한마디에 신뢰가 무너진다");

  s = content("전문가가 되기 위해 공부할 5가지",
    "'공부하라'는 말은 막연합니다. 구체적으로 무엇을 알아야 하는지 정리했습니다. 특히 4번, 만나기 전에 그 대표님 매장을 먼저 검색해 보고 가는 것만으로도 다른 영업인과 완전히 달라집니다. 2교시에 직접 실습합니다.");
  await cards(s, [
    ["FaBox", "1. 내 상품", "CMO 서비스와 상품 구성·효과·한계까지"],
    ["FaChessKnight", "2. 경쟁사", "다른 회사와 무엇이 다른지 한 문장으로"],
    ["FaStore", "3. 고객 업종", "외식업의 성수기·고민·용어"],
    ["FaMapMarkedAlt", "4. 그 매장 자체", "만나기 전 플레이스·리뷰·뉴스 확인"],
    ["FaChartBar", "5. 트렌드·사례", "플랫폼 변화, 실제 성과 사례"],
    ["FaClipboardList", "+ 나만의 노트", "자주 받는 질문과 답을 정리해 두기"],
  ], { cols: 3, h: 3.0, y: 1.35 });
  takeaway(s, "준비한 만큼 막힘이 없고, 막힘이 없는 만큼 신뢰가 쌓인다", 4.6);

  s = content("모르는 질문을 받았을 때",
    "아무리 준비해도 모르는 질문은 나옵니다. 그때 '모르는데요'로 끝내면 신뢰가 무너지고, 아는 척하면 나중에 더 크게 무너집니다. 정답은 '확인 후 약속한 시간 안에 답하기'입니다. 이렇게 하면 오히려 신뢰가 올라갑니다.");
  compare(s, ["이렇게 말하면 끝", ["\"그건 제가 모르는데요.\"", "\"그건 담당이 아니라서요.\"", "모르면서 아는 척 대충 답하기"]],
    ["이렇게 말하면 신뢰 UP", ["\"정확하게 확인해서 오늘 6시 전까지 답드리겠습니다.\"", "메모하는 모습을 보여 준다", "약속한 시간보다 먼저 답한다"]]);
  takeaway(s, "모르는 것은 약점이 아니다 — 약속을 지키지 않는 것이 약점이다");

  s = content("1교시 정리", "1교시 핵심 세 문장을 다시 읽어 주고 10분 휴식. '2교시에는 실전과 실습입니다.'");
  const k1 = [["FaFire", "영업은 하는 만큼 돌아오는 일", "최고의 보상은 성취감 — 나만의 '영업 이유'를 잊지 말자"],
    ["FaBullhorn", "마케팅은 좋은 상품을 '알리는' 일", "사라지는 가게를 살리는 일 — 고객의 성공이 나의 성공"],
    ["FaUserCheck", "고객은 사람을 산다", "첫인상 · 자신감 · 전문성으로 신뢰를 만든다"]];
  for (let i = 0; i < 3; i++) {
    const y = 1.3 + i * 1.0;
    await circleIcon(s, k1[i][0], 0.6, y + 0.08, 0.7, C.accent1);
    s.addText(k1[i][1], { ...T, x: 1.55, y, w: 7.85, h: 0.45, fontSize: 19, bold: true, color: C.text2 });
    s.addText(k1[i][2], { ...T, x: 1.55, y: y + 0.45, w: 7.85, h: 0.4, fontSize: 14, color: C.text1 });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 4.4, w: 8.8, h: 0.6, fill: { color: SOFT_GREEN }, rectRadius: 0.1, objectName: "breakBox" });
  s.addText("쉬는 시간 10분 — 2교시는 '찾아오게 만드는 영업'과 실습입니다", { ...T, x: 0.9, y: 4.4, w: 8.3, h: 0.6, fontSize: 15, bold: true, color: C.accent2, valign: "middle" });

  // =================== 2교시 ===================
  sessionSlide("2교시", "영업의 실전", "04  찾아오게 만드는 영업\n05  첫 만남부터 재계약까지\n06  먹스타와 함께하는 영업", "2교시 60분. 04파트 15분(실습② 10분 포함 시 25분), 05파트 15분(실습③ 10분 포함 시 25분), 06파트 7분, 마무리 3분.");

  sectionSlide("04", "찾아오게 만드는 영업", "사람이 있는 곳으로 가라", "모임과 소개를 통해 영업 기회를 만드는 파트.");

  s = content("기회는 사람이 있는 곳에 있다",
    "여자를 만나고 싶은데 맨날 남자만 있는 곳에 있으면 연애를 할 수 없겠죠. 비즈니스도 똑같습니다. 대표님들을 만나려면 대표님들이 모이는 곳에 가야 합니다. 저는 지금 이런 모임에 다니고 있습니다. 강남외식산업 총동문회에서는 사무차장을 맡고 있는데, 요식업 대표님만 300명입니다.");
  await cards(s, [
    ["FaUtensils", "외식산업 최고위과정", "중앙대 강남 · 총동문회 사무차장 (요식업 대표 300명)"],
    ["FaUniversity", "CADO 최고위과정", "서울과기대 최고위건축개발과정 40기 · 매주 목요일"],
    ["FaCoffee", "BNI 조찬 모임", "매주 목요일 새벽 6시 서울숲 — 소개 중심 모임"],
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

  s = content("사례: 강화도 「바다향기」 — 밥 먹다 생긴 계약",
    "최근 일입니다. CADO 워크숍으로 강화도에 갔다가 바다향기라는 식당에서 밥을 먹었습니다. 영수증을 받아서 제가 직접 영수증 리뷰를 써 드렸는데, 그 리뷰가 영수증 리뷰 1등으로 올라갔습니다. 그 화면을 사장님께 보여 드리면서 '마케팅 궁금한 거 있으시면 연락 주세요' 하고 왔습니다. 며칠 뒤 사장님이 먼저 전화를 주셨고, CMO 계약을 했습니다. 지금도 계속 함께하고 있습니다. [영수증 리뷰 사진을 받으면 이 슬라이드에 추가]");
  await flow(s, [
    ["워크숍", "CADO 워크숍으로 강화도 방문"],
    ["식사", "식당에서 밥 먹고 영수증 받기"],
    ["리뷰 1등", "직접 쓴 영수증 리뷰가 1등으로"],
    ["한마디", "화면을 보여 드리며 \"마케팅 궁금하면 연락 주세요\""],
    ["먼저 전화", "사장님이 먼저 연락 → CMO 계약, 지금도 진행 중"],
  ]);
  takeaway(s, "말로 설득하지 않았다 — 실력을 먼저 보여 주니 고객이 찾아왔다");

  s = content("소개가 소개를 낳는다",
    "고객이 들어오는 길 1위는 지인 소개입니다. 마케팅 서비스에 만족하셨기 때문입니다. 특히 BNI에서 소개받아 계약한 사례가 정말 많습니다. 그리고 그렇게 소개받은 매장이 또 다른 매장을 소개해 줘서 계약을 했습니다. 만족한 고객이 다음 고객을 데려옵니다.");
  const chain = [["FaCoffee", "BNI 모임", "신뢰 쌓기"], ["FaHandshake", "소개받은 매장 A", "계약 · 만족"], ["FaStore", "A가 소개한 매장 B", "또 계약"], ["FaUsers", "B가 소개한 매장 C…", "꼬리를 문다"]];
  for (let i = 0; i < 4; i++) {
    const x = 0.6 + i * 2.25;
    await circleIcon(s, chain[i][0], x + 0.55, 1.4, 0.95, i === 0 ? C.accent3 : C.accent1);
    s.addText(chain[i][1], { ...T, x, y: 2.5, w: 2.05, h: 0.45, fontSize: 15, bold: true, color: C.text2, align: "center" });
    s.addText(chain[i][2], { ...T, x, y: 2.95, w: 2.05, h: 0.4, fontSize: 13, color: C.text1, align: "center" });
    if (i < 3) s.addImage({ data: await icon("FaArrowRight", HEX.accent6), x: x + 1.92, y: 1.72, w: 0.3, h: 0.3, altText: "다음" });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 3.6, w: 8.8, h: 0.7, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "givers" });
  s.addText([{ text: "BNI의 철학  ", options: { bold: true, color: C.accent3 } }, { text: "Givers Gain — 주는 사람이 얻는다.  인맥(Contacts) + 소개(Referrals) = 순익(Profit)", options: { color: C.text2 } }],
    { ...T, x: 0.9, y: 3.6, w: 8.3, h: 0.7, fontSize: 15, valign: "middle" });
  takeaway(s, "고객 유입 1위는 '지인 소개' — 만족이 다음 고객을 데려온다", 4.5);

  s = content("소개가 끊이지 않는 사람의 습관",
    "내가 먼저 소개해 주고, 먼저 도와주는 사람에게 소개가 돌아옵니다. 소개받은 건은 반드시 결과를 소개해 준 분께 보고하세요. 그래야 다음 소개가 옵니다.");
  await cards(s, [
    ["FaGift", "먼저 준다", "내가 먼저 다른 대표님을 소개하고 연결한다"],
    ["FaCalendarCheck", "꾸준히 간다", "한두 번이 아니라 매주·매달 빠지지 않고"],
    ["FaReply", "48시간 안에 연락", "명함 받은 분께 이틀 안에 인사 메시지"],
    ["FaThumbsUp", "결과를 보고한다", "소개해 준 분께 \"덕분에 잘 진행됐습니다\""],
  ], { cols: 2, h: 2.9, y: 1.3 });
  takeaway(s, "Givers Gain — 먼저 주는 사람에게 기회가 돌아온다", 4.5);

  await practice("실습 ② 원투원 미팅 (BNI 방식)", 10, [
    "2명씩 짝을 짓고, 한 사람당 4분씩 서로 인터뷰한다",
    "질문: 어떤 일을 하세요? · 지금 일을 하게 된 계기는? · 가장 자랑스러운 것은?",
    "질문: 목표는 무엇인가요? · 어떤 분을 소개받으면 도움이 될까요?",
    "끝나면 '이 사람에게 소개해 줄 수 있는 한 사람'을 떠올려 적는다",
  ], "짝의 소개 포인트 1개 + 내가 연결해 줄 수 있는 사람 1명",
    "BNI 원투원 미팅 질문지를 간단히 한 실습입니다. 팁: 서로의 시간을 존중하고, 경청하고, 긍정적으로 격려합니다. 초면에는 결혼 여부 같은 사적인 질문은 삼갑니다. 정보를 얻었으면 파트너를 위한 좋은 소개를 찾아 주는 것이 원투원의 목적입니다.");

  s = content("온라인에서도 '찾아오게' 만들기",
    "모임이 오프라인 신뢰라면, SNS는 온라인 신뢰입니다. 저는 스마트폰 하나로 촬영·편집해서 총 팔로워 25만, 누적 조회수 2억 5천만을 만들었습니다. 인스타그램부터 블로그, 틱톡, 유튜브, 영수증 리뷰, 샤오홍슈, 셀러비, 당근, 티맵까지 직접 다 운영합니다. 마케팅하는 사람이 먼저 모든 채널을 직접 해 봐야 사장님께 자신 있게 말할 수 있습니다.");
  const ch = [["FaInstagram", "인스타그램"], ["FaBlog", "블로그"], ["FaTiktok", "틱톡"], ["FaYoutube", "유튜브"], ["FaReceipt", "영수증 리뷰"],
    ["FaGlobeAsia", "샤오홍슈"], ["FaStar", "셀러비"], ["FaCarrot", "당근"], ["FaMapMarkedAlt", "티맵"]];
  for (let i = 0; i < 9; i++) {
    const x = 0.6 + i * 0.98;
    await circleIcon(s, ch[i][0], x + 0.12, 1.35, 0.66, i === 0 ? C.accent1 : C.accent3);
    s.addText(ch[i][1], { ...T, x: x - 0.05, y: 2.1, w: 1.0, h: 0.35, fontSize: 11, bold: true, color: C.text2, align: "center" });
  }
  const sns = [["25만", "총 팔로워"], ["2.5억", "누적 조회수"], ["200개+", "50만 뷰 넘은 영상"]];
  sns.forEach(([n, l], i) => {
    const x = 0.6 + i * 3.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.75, w: 2.8, h: 1.5, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "sns" + i });
    s.addText(n, { ...T, x, y: 2.9, w: 2.8, h: 0.7, fontSize: 30, bold: true, color: C.accent1, align: "center", valign: "middle" });
    s.addText(l, { ...T, x, y: 3.6, w: 2.8, h: 0.4, fontSize: 14, color: C.text1, align: "center" });
  });
  takeaway(s, "스마트폰 하나로 만든 채널 — 첫 고객도 인스타그램을 보고 찾아왔다", 4.5);

  // =================== 05 실전 프로세스 ===================
  sectionSlide("05", "첫 만남부터 재계약까지", "강사의 실제 영업 방식", "강사의 실제 영업 순서를 그대로 보여 주는 파트.");

  s = content("만나기 전에 반드시 확인하는 5가지",
    "저는 방문하기 전에 반드시 이 다섯 가지를 확인합니다. 이걸 보고 가면 첫마디부터 다릅니다. '사장님 매장 플레이스를 보니까요…'로 시작할 수 있으니까요. 다음 실습에서 직접 해 봅니다.");
  const pre = [["FaListOl", "네이버 플레이스 순위", "주요 검색어에서 몇 위에 있는지"], ["FaCommentDots", "리뷰", "개수, 최근 리뷰, 별점, 사장님 답글"],
    ["FaImage", "플레이스 전체 분위기", "사진·메뉴·소개글이 잘 정리되어 있는지"], ["FaGlobe", "홈페이지 유무", "검색했을 때 공식 홈페이지가 나오는지"],
    ["FaNewspaper", "네이버 뉴스 노출", "언론 기사에 매장이 나온 적이 있는지"]];
  for (let i = 0; i < 5; i++) {
    const y = 1.25 + i * 0.66;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 8.8, h: 0.56, fill: { color: C.background2 }, rectRadius: 0.08, objectName: "check" + i });
    s.addImage({ data: await icon("FaCheckSquare", HEX.accent2), x: 0.8, y: y + 0.14, w: 0.28, h: 0.28, altText: "체크" });
    s.addImage({ data: await icon(pre[i][0], HEX.dk2), x: 1.3, y: y + 0.14, w: 0.28, h: 0.28, altText: pre[i][1] });
    s.addText(pre[i][1], { ...T, x: 1.8, y, w: 2.9, h: 0.56, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
    s.addText(pre[i][2], { ...T, x: 4.7, y, w: 4.6, h: 0.56, fontSize: 14, color: C.text1, valign: "middle" });
  }
  takeaway(s, "준비하고 간 사람은 첫마디가 다르다 — \"사장님 매장 플레이스를 보니까요…\"", 4.6);

  await practice("실습 ③ 매장 하나 사전 조사하기", 10, [
    "자주 가는 식당 하나를 정한다 (회사 근처, 동네 단골집 등)",
    "스마트폰으로 5가지 확인: 플레이스 순위 · 리뷰 · 분위기 · 홈페이지 · 뉴스",
    "잘하고 있는 점 1개, 개선하면 좋을 점 2개를 적는다",
    "'사장님, 플레이스를 보니까요…'로 시작하는 첫 문장을 써 본다",
  ], "매장 진단 메모 1장 (강점 1개 · 개선점 2개 · 첫 문장)",
    "2~3명에게 발표를 시키고 강사가 피드백합니다. '이 메모 한 장이 있으면 첫 만남에서 대화가 막히지 않는다'는 걸 체감하게 하는 것이 목적입니다.");

  s = content("첫 만남은 이렇게 흘러간다",
    "제 실제 순서입니다. 미리 조사한 내용을 바탕으로 먼저 마케팅 고민이 있는지 여쭤봅니다. 그다음 우리 회사를 소개합니다. 우리는 요식업 마케팅 전문가이고, 그중 제일 잘하는 게 마케팅 직원처럼 일해 드리는 CMO 서비스라는 걸 첫 만남에 바로 말씀드립니다. 계약이 되면 바로 하고, 안 되면 다음 만남에 계약합니다.");
  await flow(s, [
    ["사전 조사", "플레이스·리뷰·홈페이지·뉴스 확인 후 방문"],
    ["고민 묻기", "\"마케팅에서 고민되시는 게 있으세요?\""],
    ["회사 소개", "\"저희는 요식업 마케팅 전문가입니다\""],
    ["CMO 제안", "\"마케팅 직원처럼 일해 드립니다\" — 첫 만남에 바로"],
    ["계약", "그 자리에서, 안 되면 다음 만남에"],
  ]);
  takeaway(s, "듣고 → 소개하고 → 가장 잘하는 것 하나를 분명하게 제안한다");

  s = content("대표님의 마음을 여는 질문",
    "첫 만남에서 바로 상품을 설명하지 말고, 이런 질문으로 대표님의 고민을 들으세요. 대표님이 말을 많이 할수록 계약 가능성은 높아집니다.");
  const qs = ["요즘 매출에서 가장 고민되시는 부분이 어떤 건가요?", "손님들은 주로 어떻게 알고 찾아오세요?",
    "예전에 마케팅을 해 보셨다면, 어떤 점이 아쉬우셨어요?", "6개월 뒤에 매장이 어떻게 되어 있으면 좋겠습니까?",
    "근처 매장과 비교하면 우리 매장의 강점은 뭘까요?"];
  for (let i = 0; i < qs.length; i++) {
    const y = 1.3 + i * 0.68;
    await circleIcon(s, "FaQuestion", 0.6, y + 0.04, 0.48, i % 2 ? C.accent3 : C.accent1);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 1.25, y, w: 8.15, h: 0.56, fill: { color: C.background2 }, rectRadius: 0.08, objectName: "q" + i });
    s.addText(qs[i], { ...T, x: 1.45, y, w: 7.8, h: 0.56, fontSize: 15, color: C.text2, valign: "middle" });
  }

  s = content("계약은 끝이 아니라 시작이다",
    "제가 매출을 계속 낼 수 있는 이유는 저를 믿고 계속 유지해 주시는 대표님들 덕분입니다. 여주 엄마네와 큰집한우는 거의 2년째 함께하고 있습니다. 비결은 카카오톡 단톡방 소통입니다. 매일 소통하고, 매주 지난주에 한 일과 다음 주에 할 일을 보고하고, 매월 지난달 성과를 분석해서 다음 달을 기획합니다. 사장님이 묻기 전에 먼저 알려 드립니다.");
  const cycle = [["FaComments", "매일", "단톡방으로 수시 소통 — 요청은 바로 반영"], ["FaCalendarWeek", "매주", "지난주 한 일 보고 + 다음 주 할 일 예고"],
    ["FaChartPie", "매월", "지난달 광고 성과 분석 + 다음 달 마케팅 기획"]];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 3.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 2.8, h: 2.3, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "cycle" + i });
    await circleIcon(s, cycle[i][0], x + 0.25, 1.5, 0.65, [C.accent1, C.accent3, C.accent2][i]);
    s.addText(cycle[i][1], { ...T, x: x + 1.05, y: 1.55, w: 1.6, h: 0.55, fontSize: 24, bold: true, color: C.text2, valign: "middle" });
    s.addText(cycle[i][2], { ...T, x: x + 0.25, y: 2.35, w: 2.35, h: 1.1, fontSize: 14, color: C.text1, valign: "top" });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 3.8, w: 8.8, h: 0.55, fill: { color: SOFT_ORANGE }, rectRadius: 0.1, objectName: "retention" });
  s.addText([{ text: "여주 「엄마네」 · 「큰집한우」  ", options: { bold: true, color: C.accent1 } }, { text: "약 2년째 계약 유지 중", options: { color: C.text2 } }],
    { ...T, x: 0.9, y: 3.8, w: 8.3, h: 0.55, fontSize: 15, valign: "middle" });
  takeaway(s, "사장님이 묻기 전에 먼저 알려 드린다 — 그것이 2년을 만든다", 4.5);

  s = content("계약이 끊겨도 관계는 끊지 않는다",
    "요즘 경기가 어려워서 매출이 안 나오면 마케팅 비용부터 줄이십니다. 그래서 계약이 중단될 때가 있습니다. 그럴 때 저는 '나중에 마케팅 궁금한 거 있으시면 언제든 연락 주세요'라고 말씀드립니다. 시간이 좀 지나면 먼저 연락합니다. '잘 지내세요? 요즘 매출은 어떠세요?' 그리고 괜찮은 상품이 있으면 '한번 진행해 보시는 건 어떠세요?' 하고 제안합니다.");
  await flow(s, [
    ["중단 이유 이해", "경기가 어려워 비용을 줄이는 것 — 내가 싫어서가 아니다"],
    ["문 열어 두기", "\"궁금한 거 있으시면 언제든 연락 주세요\""],
    ["먼저 안부", "\"잘 지내세요? 요즘 매출은 어떠세요?\""],
    ["맞는 제안", "\"괜찮은 상품이 있는데 한번 해 보실래요?\""],
  ]);
  takeaway(s, "거절은 '끝'이 아니라 '아직' — 다음 기회는 남겨 둔 관계에서 온다");

  s = content("영업인의 하루",
    "제 실제 하루입니다. 평소에는 6시 반에 일어나서 7시 반쯤 일을 시작합니다. 매일 할 일을 적어 두고 체크리스트처럼 확인하는 습관을 들였습니다. 군대에서 배운 습관입니다. 목요일은 새벽 5시에 일어나서 6시까지 서울숲 BNI 모임에 갑니다. 낮에는 미팅, 미팅이 없으면 사무실 업무. 저녁과 밤에는 미팅이나 영상 편집을 합니다.");
  const day = [["06:30", "기상 · 준비", "FaSun"], ["07:30", "업무 시작\n오늘 할 일 체크리스트", "FaClipboardCheck"], ["낮", "미팅\n(없으면 사무 업무)", "FaHandshake"],
    ["저녁 · 밤", "미팅 또는\n영상 편집", "FaVideo"], ["목요일 05:00", "기상 → 06:00\n서울숲 BNI 조찬", "FaCoffee"]];
  for (let i = 0; i < 5; i++) {
    const x = 0.6 + i * 1.8;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.4, w: 1.6, h: 2.8, fill: { color: i === 4 ? SOFT_ORANGE : C.background2 }, rectRadius: 0.1, objectName: "day" + i });
    await circleIcon(s, day[i][2], x + 0.5, 1.6, 0.6, i === 4 ? C.accent1 : C.accent3);
    s.addText(day[i][0], { ...T, x, y: 2.4, w: 1.6, h: 0.4, fontSize: i === 4 ? 14 : 16, bold: true, color: C.text2, align: "center" });
    s.addText(day[i][1], { ...T, x: x + 0.1, y: 2.85, w: 1.4, h: 1.2, fontSize: 13, color: C.text1, align: "center", valign: "top" });
  }
  takeaway(s, "매일 할 일을 적고 체크한다 — 작은 습관이 하루 12시간을 버티게 한다", 4.45);

  s = content("영업인이 지켜야 할 약속",
    "영업은 결국 신뢰의 일입니다. 당장 계약을 위해 지키지 못할 약속을 하면, 한 번은 팔아도 두 번은 못 팝니다. 저희도 '순위나 매출을 보증하지는 않습니다'라고 솔직하게 말씀드립니다. 특히 소개로 이어지는 영업에서는 한 번의 거짓말이 소개해 준 분의 신뢰까지 무너뜨립니다.");
  await cards(s, [
    ["FaBan", "과장하지 않는다", "\"무조건 1등\" 같은 보장은 하지 않는다"],
    ["FaClock", "시간을 지킨다", "미팅·보고·답변 시간은 반드시"],
    ["FaBalanceScale", "고객 편에 선다", "필요 없는 상품은 권하지 않는다"],
    ["FaShieldAlt", "소개자를 지킨다", "소개해 준 분의 얼굴에 먹칠하지 않는다"],
  ], { cols: 2, h: 2.9, y: 1.3 });
  takeaway(s, "한 번 팔고 끝낼 사람인가, 10년 갈 파트너인가", 4.5);

  // =================== 06 먹스타와 함께하는 영업 ===================
  sectionSlide("06", "먹스타와 함께하는 영업", "우리가 파는 것, 그리고 함께 버는 구조", "회사 상품과 수수료 구조를 소개하는 파트. 직원과 외부 영업 파트너 모두 대상. (7분)");

  s = content("(주)먹스타: 외식업 마케팅 전문",
    "(주)먹스타는 외식업 마케팅 한 분야만 해 왔습니다. (주)상생어벤져스컴퍼니의 자회사입니다. 지금까지 외식업 브랜드 1,000곳과 일했고, 크리에이터 800명을 직접 관리합니다. 무엇보다 저희가 직접 식당을 운영합니다. 남의 가게를 맡기 전에, 우리 가게부터 같은 방식으로 관리합니다. 이게 영업할 때 가장 강력한 무기입니다.");
  const mk = [["1,000+", "누적 진행\n외식업 브랜드"], ["800명", "직접 관리하는\n크리에이터"], ["2.5억", "운영 채널\n누적 조회수"], ["3곳", "직접 운영하는\n직영 매장"]];
  mk.forEach(([n, l], i) => {
    const x = 0.6 + i * 2.25;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 2.05, h: 1.75, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "mk" + i });
    s.addText(n, { ...T, x, y: 1.45, w: 2.05, h: 0.75, fontSize: 30, bold: true, color: i === 3 ? C.accent2 : C.accent1, align: "center", valign: "middle" });
    s.addText(l, { ...T, x, y: 2.2, w: 2.05, h: 0.7, fontSize: 13, color: C.text1, align: "center", valign: "top" });
  });
  s.addText([
    { text: "직영 매장  ", options: { bold: true, color: C.accent2 } },
    { text: "중화객잔수 강남구청점 (검색량 110 → 1,080, 연 매출 15억) · 미친양꼬치 잠실점 (예약·주문 +416%) · 케이찹사라다 신사직영점", options: { color: C.text2 } },
  ], { ...T, x: 0.6, y: 3.3, w: 8.8, h: 0.8, fontSize: 14, valign: "top" });
  takeaway(s, "\"저희도 직접 장사합니다\" — 사장님의 마음을 아는 마케팅 회사", 4.4);

  s = content("같은 상권, 비슷한 메뉴 — 왜 한 곳만 줄을 설까?",
    "같은 상권, 비슷한 메뉴, 가격도 크게 차이가 없습니다. 그런데 어떤 가게는 항상 손님이 많고 예약이 계속 들어오고, 어떤 가게는 맛도 괜찮은데 손님이 점점 줄어듭니다. 차이는 '마케팅을 하는 가게냐, 안 하는 가게냐'입니다. 요즘 손님은 지나가다 들어오기보다 검색하고 옵니다. 이 과정에서 보이지 않는 가게는 존재하지 않는 가게와 같습니다. 사장님과 첫 만남에서 이 이야기로 시작하면 좋습니다.");
  await flow(s, [
    ["SNS에서 발견", "인스타·유튜브에서 처음 본다"],
    ["맛집 검색", "네이버에서 \"동네 + 맛집\" 검색"],
    ["리뷰·사진 확인", "위에 뜬 가게의 리뷰와 콘텐츠를 본다"],
    ["예약·방문", "마음에 들면 예약하거나 찾아온다"],
  ]);
  takeaway(s, "검색에 보이지 않는 가게는 존재하지 않는 가게와 같다");

  s = content("잘되는 가게가 꾸준히 하는 7가지",
    "잘되는 매장들은 우연히 잘되는 것이 아닙니다. 대부분 이런 것들을 꾸준히 관리하고 있습니다. 이런 마케팅이 쌓이면 가게는 자연스럽게 '검색 → 방문 → 매출' 구조가 만들어집니다. 그런데 사장님은 주방, 직원, 재료, 손님 응대만으로도 바쁩니다. 여기에 마케팅까지 직접 하기는 사실상 어렵습니다. 그래서 CMO가 필요합니다.");
  const seven = [["FaMapMarkerAlt", "플레이스 노출 관리"], ["FaCommentDots", "리뷰 관리·여론 형성"], ["FaBlog", "블로그·인플루언서"],
    ["FaSearchDollar", "검색광고 운영"], ["FaMap", "지도앱 정보 관리"], ["FaTicketAlt", "이벤트·쿠폰·예약 운영"], ["FaUsers", "지역 커뮤니티 바이럴"]];
  for (let i = 0; i < 7; i++) {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.6 + col * 2.85, y = 1.25 + row * 0.78;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.7, h: 0.66, fill: { color: C.background2 }, rectRadius: 0.08, objectName: "seven" + i });
    s.addImage({ data: await icon(seven[i][0], HEX.accent1), x: x + 0.18, y: y + 0.18, w: 0.3, h: 0.3, altText: seven[i][1] });
    s.addText(seven[i][1], { ...T, x: x + 0.62, y, w: 2.0, h: 0.66, fontSize: 13, bold: true, color: C.text2, valign: "middle" });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.5, y: 1.25, w: 2.9, h: 3.0, fill: { color: SOFT_ORANGE }, rectRadius: 0.12, objectName: "busyOwner" });
  s.addText("그런데 사장님은\n이미 바쁘다", { ...T, x: 6.75, y: 1.4, w: 2.5, h: 0.8, fontSize: 17, bold: true, color: C.accent1, valign: "top" });
  s.addText([
    { text: "주방 관리", options: { bullet: true, breakLine: true } }, { text: "직원 관리", options: { bullet: true, breakLine: true } },
    { text: "재료 관리", options: { bullet: true, breakLine: true } }, { text: "손님 응대", options: { bullet: true, breakLine: true } },
    { text: "+ 마케팅까지? 사실상 어렵다", options: { bold: true } },
  ], { ...T, x: 6.75, y: 2.25, w: 2.5, h: 1.9, fontSize: 14, color: C.text2, valign: "top", paraSpaceAfter: 4 });
  takeaway(s, "꾸준히 쌓이면 '검색 → 방문 → 매출' — 그걸 대신 해 주는 것이 CMO", 4.5);

  s = content("주력 상품: CMO 서비스",
    "가장 주력으로 하는 상품입니다. CMO는 광고 하나를 파는 게 아니라 매장의 마케팅을 총괄 관리하는 시스템입니다. 식당 예산에 맞춰서 매달 마케팅을 기획하고 실행해 드리는 서비스입니다. 마케팅 직원을 뽑으면 인건비만 월 200만 원이 넘고, 대행사를 여러 곳 쓰면 누가 뭘 했는지 알 수가 없습니다. CMO 서비스는 한 팀이 전 채널을 맡고, 단톡방 하나로 소통하고, 매주 결과로 보여 드립니다. 월 단위 계약이라 사장님 부담이 적고, 유지되면 매달 매출이 쌓입니다.");
  compare(s, ["일반 마케팅", ["한 가지 상품만 판매 (블로그만, 광고만)", "직원 채용 — 인건비만 월 200만 원 이상", "대행사 여러 곳 — 누가 뭘 했는지 모름"]],
    ["CMO 서비스", ["매장 상황에 맞는 마케팅을 총괄 운영", "마케팅 담당 직원을 한 달 단위로 두는 개념", "예산에 맞춰 매달 기획 · 단톡방 · 매주 보고"]], { h: 2.75 });
  takeaway(s, "\"마케팅 직원처럼 일해 드립니다\" — 첫 만남에서 가장 먼저 꺼내는 한 문장", 4.45);

  s = content("먹스타의 상품들", "CMO 서비스 외에 사장님 상황에 맞춰 고를 수 있는 상품들입니다. 자세한 내용은 먹스타 홈페이지(mukstar.co.kr)에 상품마다 안내 페이지가 있습니다. 가격은 상담 때 안내합니다.");
  const prods = [["FaUsers", "먹스타 PPL"], ["FaBlog", "VIP 파워블로그"], ["FaVideo", "먹스타 기자단"], ["FaGlobeAsia", "외국인 체험단"],
    ["FaFilm", "숏폼채널 제작"], ["FaGlassCheers", "먹스타파티"], ["FaStore", "프랜차이즈 마케팅"], ["FaCamera", "브랜딩 영상"],
    ["FaTv", "IPTV 광고"], ["FaChalkboardTeacher", "숏폼 클래스"], ["FaLandmark", "지원사업·바우처"], ["FaLaptop", "맛집 홈페이지"]];
  for (let i = 0; i < 12; i++) {
    const x = 0.6 + (i % 4) * 2.25, y = 1.3 + Math.floor(i / 4) * 1.05;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.05, h: 0.85, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "prod" + i });
    s.addImage({ data: await icon(prods[i][0], HEX.accent1), x: x + 0.2, y: y + 0.25, w: 0.35, h: 0.35, altText: prods[i][1] });
    s.addText(prods[i][1], { ...T, x: x + 0.68, y, w: 1.3, h: 0.85, fontSize: 13, bold: true, color: C.text2, valign: "middle" });
  }
  takeaway(s, "주력은 CMO, 나머지는 사장님 상황에 맞춰 더하는 선택지", 4.55);

  s = content("영업 수수료 구조",
    "영업하시는 분들이 가장 궁금해하시는 부분입니다. 마케팅 상품 중에 우리가 100% 직접 시행하는 상품은 마진이 높습니다. 다른 곳에 외주를 주는 상품은 마진이 적습니다. 그래서 직접 시행하는 상품을 팔수록 수수료도 더 높습니다. 구체적인 수수료율은 개별 상담 때 안내합니다.");
  const feeIcons = [await icon("FaArrowUp", HEX.accent1), await icon("FaArrowDown", HEX.accent6)];
  [["직접 시행 상품", "우리가 100% 직접 실행", "마진 높음 → 수수료 높음", C.accent1, SOFT_ORANGE, "FaArrowUp"],
   ["외주 상품", "다른 곳에 외주를 맡겨 실행", "마진 적음 → 수수료 낮음", C.accent6, C.background2, "FaArrowDown"]].forEach(([h, d, m, col, fill, ic], i) => {
    const x = 0.6 + i * 4.55;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 4.25, h: 2.6, fill: { color: fill }, rectRadius: 0.12, objectName: "fee" + i });
    s.addText(h, { ...T, x: x + 0.3, y: 1.5, w: 3.7, h: 0.5, fontSize: 22, bold: true, color: col });
    s.addText(d, { ...T, x: x + 0.3, y: 2.05, w: 3.7, h: 0.45, fontSize: 15, color: C.text1 });
    s.addImage({ data: feeIcons[i], x: x + 0.3, y: 2.85, w: 0.45, h: 0.45, altText: m });
    s.addText(m, { ...T, x: x + 0.9, y: 2.75, w: 3.2, h: 0.65, fontSize: 18, bold: true, color: col, valign: "middle" });
  });
  s.addText("※ 구체적인 수수료율은 개별 상담 때 안내합니다", { ...T, x: 0.6, y: 4.0, w: 8.8, h: 0.35, fontSize: 12, color: C.accent6 });
  takeaway(s, "우리가 직접 하는 상품을 이해하고 파는 사람이 더 많이 번다", 4.5);

  // =================== 마무리 ===================
  section = "마무리";
  pres.addSection({ title: section });
  s = content("오늘의 핵심 5가지", "오늘 내용을 다섯 문장으로 정리합니다. 이 다섯 가지만 기억하셔도 충분합니다.");
  const keys = ["영업은 하는 만큼 돌아오는 일 — 최고의 보상은 성취감", "마케팅은 좋은 상품을 '알려서' 가게를 살리는 일",
    "고객은 상품이 아니라 사람을 산다 — 첫인상·자신감·전문성", "찾아가는 영업에서 찾아오게 하는 영업으로 — 모임과 소개",
    "계약은 시작 — 매일·매주·매월 먼저 알려 드리면 2년이 간다"];
  keys.forEach((k, i) => {
    const y = 1.3 + i * 0.7;
    s.addText(String(i + 1), { ...T, x: 0.6, y, w: 0.55, h: 0.55, fontSize: 26, bold: true, color: C.accent1, valign: "middle" });
    s.addText(k, { ...T, x: 1.25, y, w: 8.15, h: 0.55, fontSize: 17, bold: i === 0, color: C.text2, valign: "middle" });
  });

  s = content("이번 주 실천 과제", "교육이 끝나고 바로 실천할 수 있는 과제입니다. 다음 만남에서 결과를 함께 나눕니다.");
  const todo = [["FaClipboardCheck", "할 일 체크리스트", "매일 아침 할 일을 적고 저녁에 체크하기"], ["FaPen", "30초 자기소개", "누구를 돕고 어떤 결과를 내는지 써서 말해 보기"],
    ["FaBook", "상품 Q&A 20개", "CMO 서비스 예상 질문 20개와 답 정리"], ["FaUsers", "모임 하나 참석", "대표님들이 모이는 모임 한 곳 찾아가기"],
    ["FaSearch", "매장 3곳 조사", "실습③ 방식으로 3곳 진단 메모 만들기"], ["FaHeart", "한 사람 돕기", "대가 없이 누군가를 한 명 소개·연결하기"]];
  await cards(s, todo, { cols: 3, h: 3.0, y: 1.35, accent: C.accent2 });

  s = pres.addSlide({ masterName: "COVER", sectionTitle: section });
  s.addText("하는 만큼 성취하는 일,", { placeholder: "title" });
  s.addText("영업 파트너로 함께하세요", { ...T, x: 0.6, y: 2.25, w: 8.8, h: 0.8, fontSize: 36, bold: true, color: C.accent1 });
  s.addText("질문과 나눔", { ...T, x: 0.6, y: 3.3, w: 8.8, h: 0.45, fontSize: 20, bold: true, color: C.background1 });
  s.addText([
    { text: "이인선 상무이사  |  (주)상생어벤져스컴퍼니 · (주)먹스타", options: { breakLine: true } },
    { text: "Instagram @taste_goyang   ·   010-4754-1667" },
  ], { ...T, x: 0.6, y: 4.1, w: 8.8, h: 0.8, fontSize: 15, color: MUTED_ON_DARK, paraSpaceAfter: 4 });
  s.addNotes("마무리: '저는 20년 동안 성취감 없이 살았습니다. 연금이 나와도 지금이 훨씬 행복합니다. 여러분도 그 기쁨을 느끼셨으면 좋겠습니다. 함께 영업하고 싶으신 분은 언제든 연락 주세요.' 이후 질의응답.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
