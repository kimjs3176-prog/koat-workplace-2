// kordoc(https://github.com/chrisryugj/kordoc, MIT) 연동 — 한국 행정 공문서 서식 HWPX 생성·표기법 점검.
// Vercel: api/kordoc.mjs 가 이 모듈을 부른다. 로컬: kordoc_cli.mjs 를 Flask(kordoc_bridge.py)가 하위 프로세스로 부른다.
import { markdownToHwpx, lintGongmunText } from "kordoc"
import JSZip from "jszip"

// 문서 종류 → kordoc 공문서 프리셋(공문서 모드). 규정안·신구조문대비표는 밑줄 표시가 필요해 Python 생성기를 쓴다.
const PRESETS = new Set(["기안문", "보고서", "계획서", "통지", "회의록", "개조식"])
const MAX_MD = 400_000, MAX_B64 = 4_000_000, MAX_FILES = 12, MAX_LINT = 10

const safeName = (s, ext) => (String(s || "문서").replace(/[\\/:*?"<>|\x00-\x1f]/g, "_").slice(0, 80) || "문서") + ext
const bad = (error, status = 400) => ({ status, json: { success: false, error } })

async function bundle(body) {
  const files = Array.isArray(body.files) ? body.files.filter(f => f && typeof f === "object").slice(0, MAX_FILES) : []
  if (!files.length) return bad("만들 문서가 없습니다.")
  const out = [], warnings = []
  for (const f of files) {
    const name = safeName(f.name, ".hwpx")
    if (typeof f.data_b64 === "string") {                 // 이미 만든 HWPX(규정안·대비표) — 묶음에만 넣는다
      if (f.data_b64.length > MAX_B64) return bad(`${name}: 파일이 너무 큽니다.`, 413)
      out.push({ name, data: Buffer.from(f.data_b64, "base64") })
      continue
    }
    const md = typeof f.markdown === "string" ? f.markdown : ""
    if (!md.trim()) continue
    if (md.length > MAX_MD) return bad(`${name}: 문서가 너무 큽니다.`, 413)
    const preset = PRESETS.has(f.preset) ? f.preset : null
    const w = []
    const buf = await markdownToHwpx(md, preset ? { gongmun: { preset }, warnings: w } : { warnings: w })
    w.forEach(x => warnings.push(`${name}: ${x}`))
    out.push({ name, data: Buffer.from(buf) })
  }
  if (!out.length) return bad("만들 문서가 없습니다.")
  if (out.length === 1) return { status: 200, file: out[0].data, type: "application/hwp+zip", filename: out[0].name, warnings }
  const zip = new JSZip()
  const seen = {}
  for (const f of out) {                                  // 같은 이름이면 (2)를 붙인다
    let n = f.name
    if (seen[n]) n = n.replace(/\.hwpx$/, `(${++seen[n]}).hwpx`); else seen[n] = 1
    zip.file(n, f.data)
  }
  const data = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" })
  return { status: 200, file: data, type: "application/zip", filename: safeName(body.filename || "문서세트", ".zip"), warnings }
}

function lint(body) {
  const texts = body.texts && typeof body.texts === "object" && !Array.isArray(body.texts) ? body.texts : {}
  const results = {}
  for (const [k, v] of Object.entries(texts).slice(0, MAX_LINT)) {
    if (typeof v !== "string") continue
    results[String(k).slice(0, 40)] = lintGongmunText(v.slice(0, MAX_MD))
      .map(f => ({ line: f.line, rule: f.rule, severity: f.severity, match: String(f.match || "").slice(0, 80), message: f.message, suggest: f.suggest || "" }))
  }
  return { status: 200, json: { success: true, results } }
}

export async function handle(action, body) {
  body = body && typeof body === "object" && !Array.isArray(body) ? body : {}
  try {
    if (action === "status") return { status: 200, json: { success: true, engine: "kordoc" } }
    if (action === "lint") return lint(body)
    if (action === "bundle") return await bundle(body)
    return bad("알 수 없는 요청입니다.", 404)
  } catch (e) {
    console.error("[kordoc]", e)
    return bad("공문서 파일을 만들지 못했습니다.", 500)
  }
}
