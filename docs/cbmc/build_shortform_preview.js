const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require("/root/.claude/skills/synced/1a62ff30-a17b-4a9d-bb46-a287bcb80359_f6686bbd-ce69-4d88-ac53-ac3e093346d8/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "deck.pptx";
// "capcut" (편집 앱 버전) | "insta" (인스타그램에서 바로 만드는 버전)
const VARIANT = process.argv[3] || "capcut";
const INSTA = VARIANT === "insta";
const FONT = "맑은 고딕";
const THEME = {
  name: "CBMC Shortform",
  headFontFace: FONT,
  bodyFontFace: FONT,
  colors: {
    dk1: "1A2440", lt1: "FFFFFF", dk2: "14306B", lt2: "EEF4FA",
    accent1: "1E9BD7", accent2: "F5A623", accent3: "14306B", accent4: "5BC0BE",
    accent5: "E85D75", accent6: "8A94A6", hlink: "1E9BD7", folHlink: "14306B",
  },
};
const HEX = THEME.colors;

async function icon(name, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(fa[name], { color: "#" + color, size: String(size) })
  );
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10 x 5.625
  pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
  pres.title = "숏폼강의 예고 - 양재CBMC";
  pres.author = "양재CBMC";
  const C = pres.SchemeColor;

  pres.defineSlideMaster({
    title: "DARK",
    background: { color: HEX.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.6, w: 5.6, h: 1.6, fontSize: 40, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "DARK_WIDE",
    background: { color: HEX.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.35, w: 8.8, h: 0.8, fontSize: 36, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: HEX.lt1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 8.8, h: 0.75, fontSize: 30, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "양재CBMC  |  제1494회 토요기도회", options: { x: 0.6, y: 5.2, w: 5, h: 0.3, fontSize: 10, color: C.accent6, margin: 0 } } },
    ],
    slideNumber: { x: 9.0, y: 5.2, w: 0.4, h: 0.3, fontSize: 10, color: C.accent6, align: "right" },
  });

  // ---------- Slide 1: Title ----------
  pres.addSection({ title: "예고" });
  let s = pres.addSlide({ masterName: "DARK", sectionTitle: "예고" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 0.7, w: 2.3, h: 0.45, fill: { color: C.accent2 }, rectRadius: 0.22, objectName: "tag" });
  s.addText("다음 모임 예고", { x: 0.6, y: 0.7, w: 2.3, h: 0.45, fontSize: 16, bold: true, color: C.text2, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText("1분이면 충분합니다", { placeholder: "title" });
  s.addText("숏폼으로 일터에서 복음을 전하라", { x: 0.6, y: 2.75, w: 5.8, h: 0.6, fontSize: 22, color: C.accent4, bold: true, margin: 0, isTextBox: true });
  s.addText([
    { text: "11월 21일(토) 차기모임 · 숏폼강의 | 강사 이인선 대표", options: { breakLine: true } },
    { text: "\"너희는 온 천하에 다니며 만민에게 복음을 전파하라\" (막 16:15)" },
  ], { x: 0.6, y: 3.75, w: 5.8, h: 0.9, fontSize: 14, color: C.background2, margin: 0, paraSpaceAfter: 6, isTextBox: true });
  // phone mockup
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.0, y: 0.55, w: 2.3, h: 4.5, fill: { color: "0D1B3D" }, line: { color: C.accent1, width: 3 }, rectRadius: 0.3, objectName: "phone" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.15, y: 0.8, w: 2.0, h: 4.0, fill: { color: C.accent1 }, rectRadius: 0.15, objectName: "screen" });
  s.addShape(pres.shapes.OVAL, { x: 7.75, y: 2.0, w: 0.8, h: 0.8, fill: { color: C.background1 }, objectName: "playCircle" });
  s.addImage({ data: await icon("FaPlay", HEX.accent1), x: 8.0, y: 2.22, w: 0.36, h: 0.36, altText: "재생 아이콘" });
  s.addText("0:59", { x: 7.15, y: 3.05, w: 2.0, h: 0.4, fontSize: 18, bold: true, color: C.background1, align: "center", margin: 0, isTextBox: true });
  s.addText("#일터선교 #CBMC", { x: 7.15, y: 4.2, w: 2.0, h: 0.4, fontSize: 11, color: C.background1, align: "center", margin: 0, isTextBox: true });
  s.addNotes("오늘은 다음 모임(11월 21일)에 진행할 숏폼강의를 미리 소개합니다. 핵심 메시지는 '1분이면 충분하다'입니다. 스마트폰 하나로 일터에서 복음과 킹덤컴퍼니의 가치를 전할 수 있습니다.");

  // ---------- Slide 1b: Speaker ----------
  pres.addSection({ title: "강사 소개" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "강사 소개" });
  s.addText("강사 소개", { placeholder: "title" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.25, w: 2.9, h: 3.7, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "photoCard" });
  s.addImage({ path: require("path").join(__dirname, "speaker.jpg"), x: 0.75, y: 1.4, w: 2.6, h: 2.92, altText: "이인선 강사 사진", objectName: "speakerPhoto" });
  s.addText("맛고양  이인선", { x: 0.75, y: 4.4, w: 2.6, h: 0.45, fontSize: 18, bold: true, color: C.text2, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText([
    { text: "맛고양 채널주  ·  (주)먹스타 대표이사", options: { breakLine: true } },
    { text: "現 (주)상생어벤져스 상무이사" },
  ], { x: 3.9, y: 1.25, w: 5.5, h: 0.65, fontSize: 14, bold: true, color: C.accent1, margin: 0, valign: "top", isTextBox: true });
  const stats = [["400+", "숏폼 마케팅\n진행 업체"], ["2.5억+", "숏폼 누적\n조회수"], ["25만+", "10개 채널\n팔로워"], ["100회+", "숏폼마케팅\n강의"]];
  for (let i = 0; i < 4; i++) {
    const x = 3.9 + i * 1.4;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.05, w: 1.28, h: 1.3, fill: { color: C.background2 }, rectRadius: 0.1, objectName: "statCard" + i });
    s.addText(stats[i][0], { x, y: 2.15, w: 1.28, h: 0.5, fontSize: 20, bold: true, color: i === 1 ? C.accent2 : C.text2, align: "center", valign: "middle", margin: 0, isTextBox: true });
    s.addText(stats[i][1], { x, y: 2.65, w: 1.28, h: 0.6, fontSize: 11, color: C.text1, align: "center", valign: "top", margin: 0, isTextBox: true });
  }
  s.addText([
    { text: "SBA경제진흥원 · 소상공인진흥공단 숏폼마케팅 강사", options: { bullet: true, breakLine: true } },
    { text: "명륜진사갈비 등 400개 업체 숏폼 마케팅 진행", options: { bullet: true, breakLine: true } },
    { text: "먹스타 커뮤니티 운영, CU·당근 공식 인플루언서", options: { bullet: true, breakLine: true } },
    { text: "SNS마케팅 전문가 1급, 중앙대 외식경영 최고경영자과정", options: { bullet: true } },
  ], { x: 3.9, y: 3.55, w: 5.5, h: 1.45, fontSize: 13, color: C.text1, margin: 0, valign: "top", paraSpaceAfter: 5, isTextBox: true });
  s.addNotes("다음 모임 강사님을 소개합니다. 맛집 채널 '맛고양'을 운영하는 이인선 대표님입니다. 400개가 넘는 업체의 숏폼 마케팅을 진행했고, 누적 조회수 2억 5천만 회 이상, 10개 채널 팔로워 25만 명 이상을 보유한 현장 전문가입니다. SBA경제진흥원과 소상공인진흥공단 등에서 100회 이상 강의하셨습니다.");

  // ---------- Slide 2: Why shortform ----------
  pres.addSection({ title: "왜 숏폼인가" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "왜 숏폼인가" });
  s.addText("왜 지금 숏폼인가", { placeholder: "title" });
  s.addText("사람들이 머무는 곳이 바뀌었습니다. 복음을 전할 자리도 함께 넓어졌습니다.", { x: 0.6, y: 1.1, w: 8.8, h: 0.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true });
  const why = [
    ["FaClock", "15~60초", "짧은 시간", "바쁜 동료·고객도 끝까지 보는 길이"],
    ["FaMobileAlt", "9 : 16", "세로 화면", "스마트폰으로 보고, 스마트폰으로 만든다"],
    ["FaShareAlt", "1번의 공유", "전파력", "카톡·유튜브·인스타로 한 번에 퍼진다"],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 3.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.75, w: 2.7, h: 3.1, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "whyCard" + i });
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 2.0, w: 0.7, h: 0.7, fill: { color: C.accent1 }, objectName: "whyIconBg" + i });
    s.addImage({ data: await icon(why[i][0], HEX.lt1), x: x + 0.47, y: 2.17, w: 0.36, h: 0.36, altText: why[i][2] });
    s.addText(why[i][1], { x: x + 0.3, y: 2.9, w: 2.2, h: 0.7, fontSize: 30, bold: true, color: C.text2, margin: 0, isTextBox: true });
    s.addText(why[i][2], { x: x + 0.3, y: 3.6, w: 2.2, h: 0.4, fontSize: 16, bold: true, color: C.accent1, margin: 0, isTextBox: true });
    s.addText(why[i][3], { x: x + 0.3, y: 4.0, w: 2.2, h: 0.7, fontSize: 13, color: C.text1, margin: 0, valign: "top", isTextBox: true });
  }
  s.addNotes("숏폼은 15초~60초 길이의 세로형 영상입니다. 유튜브 쇼츠, 인스타그램 릴스, 틱톡 등이 대표적입니다. 길게 설명하지 않아도, 한 장면과 한 문장으로 마음을 움직일 수 있습니다.");

  // ---------- Slide 3: Verse ----------
  pres.addSection({ title: "말씀과 연결" });
  s = pres.addSlide({ masterName: "DARK_WIDE", sectionTitle: "말씀과 연결" });
  s.addImage({ data: await icon("FaQuoteLeft", HEX.accent2), x: 0.6, y: 0.6, w: 0.6, h: 0.6, altText: "인용 부호" });
  s.addText("숏폼은 오늘의 '온 천하'입니다", { placeholder: "title" });
  s.addText("\"너희는 온 천하에 다니며 만민에게 복음을 전파하라\"  — 마가복음 16:15", { x: 0.6, y: 2.3, w: 8.8, h: 0.5, fontSize: 18, italic: true, color: C.accent2, margin: 0, isTextBox: true });
  const conn = [
    ["2026 한국CBMC 사역주제", "일터에서 복음을 전파하자"],
    ["2026 양재지회 사업주제", "새 계명을 주노니 서로 사랑하라"],
    ["숏폼강의의 목표", "내 일터의 이야기로 동료를 사랑하고 초대하기"],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 3.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 3.25, w: 2.7, h: 1.6, fill: { color: "22427F" }, rectRadius: 0.12, objectName: "connCard" + i });
    s.addText(conn[i][0], { x: x + 0.2, y: 3.4, w: 2.3, h: 0.4, fontSize: 12, color: C.accent4, bold: true, margin: 0, isTextBox: true });
    s.addText(conn[i][1], { x: x + 0.2, y: 3.8, w: 2.3, h: 0.9, fontSize: 16, color: C.background1, bold: true, margin: 0, valign: "top", isTextBox: true });
  }
  s.addNotes("숏폼강의는 단순한 영상 기술 교육이 아닙니다. 올해 한국CBMC 사역주제 '일터에서 복음을 전파하자'와 양재지회 사업주제 '새 계명을 주노니 서로 사랑하라'를 실천하는 도구입니다.");

  // ---------- Slide 4: Curriculum 2x2 ----------
  pres.addSection({ title: "강의 내용" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "강의 내용" });
  s.addText("다음 모임에서 배울 4가지", { placeholder: "title" });
  const cur = [
    ["FaLightbulb", "1. 숏폼 이해하기", "쇼츠·릴스·틱톡의 특징과 '끝까지 보게 만드는' 원리"],
    ["FaPen", "2. 1분 대본 쓰기", "훅 - 메시지 - 초대, 3단 공식으로 나만의 대본 완성"],
    INSTA
      ? ["FaInstagram", "3. 인스타그램으로 바로", "현장 실습: 앱 하나로 촬영·자막·음악까지 (편집 앱 설치 없음)"]
      : ["FaVideo", "3. 스마트폰 촬영·편집", "현장 실습: 세로 촬영, 자막·음악 넣기 (CapCut 등 무료 앱)"],
    ["FaBuilding", "4. 킹덤컴퍼니에 적용", "회사 소개, 일터 간증, VIP 초대 영상으로 바로 활용"],
  ];
  for (let i = 0; i < 4; i++) {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.6 + col * 4.5, y = 1.35 + row * 1.85;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 4.3, h: 1.6, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "curCard" + i });
    s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: y + 0.3, w: 0.75, h: 0.75, fill: { color: i === 2 ? C.accent2 : C.accent1 }, objectName: "curIconBg" + i });
    s.addImage({ data: await icon(cur[i][0], HEX.lt1), x: x + 0.44, y: y + 0.49, w: 0.37, h: 0.37, altText: cur[i][1] });
    s.addText(cur[i][1], { x: x + 1.2, y: y + 0.2, w: 2.95, h: 0.45, fontSize: 18, bold: true, color: C.text2, margin: 0, isTextBox: true });
    s.addText(cur[i][2], { x: x + 1.2, y: y + 0.65, w: 2.95, h: 0.8, fontSize: 13, color: C.text1, margin: 0, valign: "top", isTextBox: true });
  }
  s.addNotes("강의는 이해 → 기획 → 실습 → 적용의 네 단계로 진행됩니다. 3번 실습 시간에는 각자 스마트폰으로 직접 짧은 영상을 만들어 봅니다.");

  // ---------- Slide 5: 3-step formula ----------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "강의 내용" });
  s.addText("미리 보는 '1분 숏폼' 3단 공식", { placeholder: "title" });
  const steps = [
    ["훅 (HOOK)", "처음 3초", "\"사장님, 직원이 먼저 출근하는 회사 비결이 뭔가요?\"", C.accent2],
    ["메시지", "30~45초", "내 일터에서 경험한 하나님의 은혜, 한 장면 한 문장", C.accent1],
    ["초대", "마지막 5초", "\"이번 토요일 아침, CBMC에서 함께해요\"", C.text2],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 3.05;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.4, w: 2.65, h: 0.9, fill: { color: steps[i][3] }, rectRadius: 0.12, objectName: "stepHead" + i });
    s.addText([
      { text: steps[i][0], options: { fontSize: 18, bold: true, breakLine: true } },
      { text: steps[i][1], options: { fontSize: 13 } },
    ], { x, y: 1.4, w: 2.65, h: 0.9, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.45, w: 2.65, h: 1.7, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "stepBody" + i });
    s.addText(steps[i][2], { x: x + 0.2, y: 2.6, w: 2.25, h: 1.4, fontSize: 14, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
    if (i < 2) s.addImage({ data: await icon("FaChevronRight", HEX.accent6), x: x + 2.72, y: 1.7, w: 0.26, h: 0.3, altText: "다음 단계" });
  }
  s.addText("다음 모임에서는 이 공식으로 각자 30초짜리 '나의 일터 이야기'를 직접 만들어 봅니다.", { x: 0.6, y: 4.4, w: 8.8, h: 0.5, fontSize: 14, bold: true, color: C.accent1, margin: 0, isTextBox: true });
  s.addNotes("가장 중요한 것은 첫 3초입니다. 질문이나 의외의 한마디로 시작하고, 내 일터의 실제 이야기를 짧게 전한 뒤, 마지막에 반드시 초대의 말로 마무리합니다. 예시는 강의에서 더 다양하게 보여 드립니다.");

  // ---------- Slide 5b (insta only): Reels in 5 steps ----------
  if (INSTA) {
    s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "강의 내용" });
    s.addText("인스타그램 릴스, 5단계면 끝", { placeholder: "title" });
    const rs = [
      ["FaPlusSquare", "＋ 누르기", "인스타그램을 열고 아래쪽 ＋ 버튼"],
      ["FaFilm", "릴스 선택", "화면 아래에서 '릴스'를 누르기"],
      ["FaVideo", "찍기", "가운데 동그란 버튼을 눌러 촬영"],
      ["FaFont", "글씨·음악", "'텍스트'로 큰 자막, '음악'으로 찬양"],
      ["FaShare", "공유", "'공유'를 누르면 완성!"],
    ];
    for (let i = 0; i < 5; i++) {
      const x = 0.6 + i * 1.78;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 1.62, h: 3.0, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "reelStep" + i });
      s.addShape(pres.shapes.OVAL, { x: x + 0.46, y: 1.5, w: 0.7, h: 0.7, fill: { color: i === 4 ? C.accent2 : C.accent1 }, objectName: "reelNum" + i });
      s.addText(String(i + 1), { x: x + 0.46, y: 1.5, w: 0.7, h: 0.7, fontSize: 24, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
      s.addImage({ data: await icon(rs[i][0], HEX.dk2), x: x + 0.56, y: 2.4, w: 0.5, h: 0.5, altText: rs[i][1] });
      s.addText(rs[i][1], { x: x + 0.1, y: 3.0, w: 1.42, h: 0.45, fontSize: 17, bold: true, color: C.text2, align: "center", margin: 0, isTextBox: true });
      s.addText(rs[i][2], { x: x + 0.12, y: 3.45, w: 1.38, h: 0.8, fontSize: 13, color: C.text1, align: "center", valign: "top", margin: 0, isTextBox: true });
    }
    s.addText("따로 설치할 앱이 없습니다. 이미 쓰시는 인스타그램 하나면 충분합니다!", { x: 0.6, y: 4.5, w: 8.8, h: 0.5, fontSize: 15, bold: true, color: C.accent1, margin: 0, isTextBox: true });
    s.addNotes("인스타그램 앱 안에서 바로 릴스를 만드는 순서입니다. 1) 아래 ＋ 버튼, 2) 릴스 선택, 3) 동그란 버튼으로 촬영하거나 사진첩의 영상을 고릅니다, 4) '텍스트'로 큰 글씨 자막을 넣고 '음악'에서 찬양을 고릅니다, 5) '공유'를 누르면 끝입니다. 앱 버전에 따라 버튼 위치가 조금 다를 수 있으니, 현장에서 한 분씩 함께 따라 해 봅니다.");
  }

  // ---------- Slide 6: Use cases ----------
  pres.addSection({ title: "활용" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "활용" });
  s.addText("이렇게 활용할 수 있습니다", { placeholder: "title" });
  const uses = [
    ["FaBuilding", "우리 회사 소개", "킹덤컴퍼니의 가치(고객·구성원·지역사회 섬김)를 1분에 담기"],
    ["FaPrayingHands", "30초 일터 간증", "위기의 순간, 기도로 경험한 은혜를 한 장면으로"],
    ["FaUserPlus", "VIP 초대 영상", "C3포럼·토요모임 초대장을 영상으로 - VIP 정착 100명 목표"],
    ["FaCamera", "모임 스케치", "토요기도회·한국대회 현장을 회원과 가족에게 공유"],
  ];
  for (let i = 0; i < 4; i++) {
    const y = 1.3 + i * 0.95;
    s.addShape(pres.shapes.OVAL, { x: 0.6, y: y + 0.05, w: 0.65, h: 0.65, fill: { color: C.accent1 }, objectName: "useIconBg" + i });
    s.addImage({ data: await icon(uses[i][0], HEX.lt1), x: 0.76, y: y + 0.21, w: 0.33, h: 0.33, altText: uses[i][1] });
    s.addText(uses[i][1], { x: 1.5, y, w: 2.4, h: 0.75, fontSize: 18, bold: true, color: C.text2, valign: "middle", margin: 0, isTextBox: true });
    s.addText(uses[i][2], { x: 3.9, y, w: 5.5, h: 0.75, fontSize: 14, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  }
  s.addNotes("숏폼은 양재지회 올해 열매 목표인 VIP 정착 100명, 그리고 C3포럼 확산과 직접 연결됩니다. 회원사 홍보와 전도가 하나의 영상으로 이루어질 수 있습니다.");

  // ---------- Slide 7: Prep checklist ----------
  pres.addSection({ title: "준비" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "준비" });
  s.addText("11월 21일, 이것만 준비해 오세요", { placeholder: "title" });
  const prep = [
    ["FaBatteryFull", "충전된 스마트폰", "실습은 모두 스마트폰으로 합니다"],
    INSTA
      ? ["FaInstagram", "인스타그램 로그인", "아이디·비밀번호 메모해 오기 - 계정이 없으면 현장에서 함께 만듭니다"]
      : ["FaDownload", "무료 편집 앱 설치", "CapCut(캡컷) 미리 설치 - 어려우면 현장에서 도와드립니다"],
    ["FaCommentDots", "회사 소개 한 문장", "\"우리 회사는 ______ 로 이웃을 섬깁니다\""],
    ["FaHeart", "간증 한 장면", "일터에서 하나님의 은혜를 경험한 순간 하나 떠올리기"],
  ];
  for (let i = 0; i < 4; i++) {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.6 + col * 4.5, y = 1.35 + row * 1.5;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 4.3, h: 1.3, fill: { color: C.background2 }, rectRadius: 0.12, objectName: "prepCard" + i });
    s.addImage({ data: await icon(prep[i][0], HEX.accent1), x: x + 0.3, y: y + 0.4, w: 0.5, h: 0.5, altText: prep[i][1] });
    s.addText(prep[i][1], { x: x + 1.05, y: y + 0.15, w: 3.1, h: 0.45, fontSize: 17, bold: true, color: C.text2, margin: 0, isTextBox: true });
    s.addText(prep[i][2], { x: x + 1.05, y: y + 0.6, w: 3.1, h: 0.6, fontSize: 13, color: C.text1, margin: 0, valign: "top", isTextBox: true });
  }
  s.addText("잘 찍는 기술보다 진솔한 이야기가 더 중요합니다. 처음이셔도 괜찮습니다!", { x: 0.6, y: 4.4, w: 8.8, h: 0.5, fontSize: 14, bold: true, color: C.accent1, margin: 0, isTextBox: true });
  s.addNotes((INSTA ? "새 앱을 설치하실 필요가 없습니다. 인스타그램 아이디와 비밀번호만 메모해 오시면, 현장에서 한 분씩 도와드리며 함께 만들어 봅니다. 자녀나 손주에게 미리 로그인을 부탁해 두셔도 좋습니다." : "연세가 있으신 회원분들도 부담 갖지 않으셔도 됩니다. 앱 설치가 어려우면 현장에서 함께 설치해 드립니다."));

  // ---------- Slide 8: Closing ----------
  pres.addSection({ title: "안내" });
  s = pres.addSlide({ masterName: "DARK", sectionTitle: "안내" });
  s.addText("VIP와 함께 오세요!", { x: 0.6, y: 0.9, w: 4.6, h: 0.8, fontSize: 36, bold: true, color: C.background1, margin: 0, valign: "middle", isTextBox: true });
  s.addText("동료·거래처 대표님께 이 모임을 소개해 주세요.\n함께 만든 1분이 누군가에게는 복음의 첫 걸음이 됩니다.", { x: 0.6, y: 1.95, w: 4.4, h: 1.2, fontSize: 15, color: C.background2, margin: 0, valign: "top", isTextBox: true });
  s.addText("서로 사랑하라 (요 13:34)", { x: 0.6, y: 3.45, w: 4.4, h: 0.4, fontSize: 16, bold: true, italic: true, color: C.accent2, margin: 0, isTextBox: true });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 5.4, y: 0.6, w: 4.0, h: 4.3, fill: { color: C.background1 }, rectRadius: 0.15, objectName: "infoCard" });
  const info = [
    ["FaCalendarAlt", "일시", "11월 21일(토) 차기모임"],
    ["FaVideo", "강의", "숏폼강의 + 실습\n강사 이인선 대표"],
    ["FaMapMarkerAlt", "장소", "하나교회 2층\n서초구 방배천로16길 17"],
    ["FaSubway", "교통", "이수역 6번 · 사당역 11번 출구"],
    ["FaHandsHelping", "섬김", "3조"],
  ];
  let iy = 0.85;
  for (const [ic, k, v] of info) {
    const h = v.includes("\n") ? 0.95 : 0.7;
    s.addImage({ data: await icon(ic, HEX.accent1), x: 5.7, y: iy + 0.08, w: 0.32, h: 0.32, altText: k });
    s.addText(k, { x: 6.2, y: iy, w: 0.7, h: 0.48, fontSize: 14, bold: true, color: C.accent1, margin: 0, valign: "middle", isTextBox: true });
    s.addText(v, { x: 6.9, y: iy, w: 2.35, h: h - 0.15, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true, paraSpaceBefore: 0 });
    iy += h;
  }
  s.addNotes("다음 모임은 11월 21일 토요일, 하나교회 2층입니다. 섬김조는 3조입니다. 오늘 소개해 드린 준비물 꼭 챙겨 오시고, 주변의 VIP 한 분과 함께 오시기를 부탁드립니다.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
