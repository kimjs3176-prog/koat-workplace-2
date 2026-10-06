// Vercel 서버리스(Node) 진입점 — /api/kordoc/<action>. 실제 처리는 kordoc_core.mjs
import { handle } from "../kordoc_core.mjs"

export const config = { maxDuration: 30 }

export default async function handler(req, res) {
  // vercel.json 이 ?action=… 으로 넘긴다(직접 호출 시에는 경로 끝 부분)
  const url = new URL(String(req.url || "/"), "http://x")
  const action = url.searchParams.get("action") || url.pathname.replace(/\/+$/, "").split("/").pop()
  let body = req.body
  if (typeof body === "string") { try { body = JSON.parse(body) } catch { body = {} } }
  const r = await handle(action, req.method === "POST" ? body : {})
  res.setHeader("X-Content-Type-Options", "nosniff")
  if (r.file) {
    res.setHeader("Content-Type", r.type)
    res.setHeader("Content-Disposition", "attachment; filename*=UTF-8''" + encodeURIComponent(r.filename))
    if (r.warnings && r.warnings.length) res.setHeader("X-Kordoc-Warnings", encodeURIComponent(r.warnings.slice(0, 5).join(" | ")).slice(0, 1500))
    res.statusCode = r.status
    return res.end(r.file)
  }
  res.statusCode = r.status
  res.setHeader("Content-Type", "application/json; charset=utf-8")
  res.end(JSON.stringify(r.json))
}
