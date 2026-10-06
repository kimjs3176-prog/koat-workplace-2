// 로컬(Flask) 실행용: node kordoc_cli.mjs <action> < 요청JSON → 응답 JSON(파일은 base64) 한 줄
import { handle } from "./kordoc_core.mjs"
let raw = ""
process.stdin.setEncoding("utf8")
process.stdin.on("data", c => { raw += c })
process.stdin.on("end", async () => {
  let body = {}
  try { body = JSON.parse(raw || "{}") } catch { body = {} }
  const r = await handle(process.argv[2] || "", body)
  const out = r.file ? { status: r.status, type: r.type, filename: r.filename, warnings: r.warnings || [], b64: r.file.toString("base64") }
    : { status: r.status, json: r.json }
  process.stdout.write(JSON.stringify(out))
})
