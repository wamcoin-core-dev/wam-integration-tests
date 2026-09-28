"use strict";
const $ = (id) => document.getElementById(id);
const labels = {pending:"Chờ thanh toán",partially_paid:"Đã trả một phần",confirming:"Chờ xác nhận",paid:"Đã thanh toán",expired:"Hết hạn",partial_expired:"Thiếu tiền · hết hạn",late_paid:"Trả muộn · cần xem"};
let token = "", mode = "", selected = null, offset = 0, timer = null, epoch = 0;
let createAttempt = null;
function notice(message = "") { $("notice").textContent = message; }
function date(seconds) { return seconds ? new Date(seconds * 1000).toLocaleString("vi-VN") : "Chưa đồng bộ"; }
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, {...options, signal: controller.signal, headers: {"Authorization": `Bearer ${token}`, ...options.headers}});
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 401) lock();
      throw new Error(result.error || "Không kết nối được ứng dụng");
    }
    return result;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Ứng dụng phản hồi chậm. Dữ liệu có thể đã cũ; anh thử lại sau.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
function post(path, body, headers = {}) { return api(path, {method:"POST", headers:{"Content-Type":"application/json", ...headers}, body:JSON.stringify(body)}); }
function badge(el, status, fresh = true) {
  el.textContent = labels[status] || status;
  el.className = "badge " + (status === "paid" && fresh ? "paid" : "warn");
}
function lock() {
  epoch++; token = ""; selected = null; createAttempt = null;
  clearTimeout(timer); $("login").hidden = false; $("dashboard").hidden = true; $("logout").hidden = true;
  $("token").value = ""; $("rows").replaceChildren(); $("payments").replaceChildren();
  $("address").textContent = ""; $("detail").hidden = true;
}
$("logout").addEventListener("click", lock);
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); token = $("token").value.trim(); const attempt = ++epoch;
  try {
    await api("/api/status");
    if (attempt !== epoch) return;
    $("token").value = ""; $("login").hidden = true; $("dashboard").hidden = false; $("logout").hidden = false;
    offset = 0; notice(); await refresh(); schedule();
  } catch (error) { notice(error.message); }
});
function schedule() {
  clearTimeout(timer);
  if (token) timer = setTimeout(async () => { try { await refresh(); } catch(error) { markStale(); notice(error.message); } schedule(); }, 5000);
}
function markStale() {
  $("node-state").textContent = "Mất kết nối · dữ liệu có thể đã cũ";
  $("detail-warning").textContent = "Không xác minh được trạng thái hiện tại. Chờ kết nối lại trước khi giao hàng.";
  for (const b of document.querySelectorAll("#rows .badge, #detail-state")) b.className = "badge warn";
}
async function refresh() {
  const generation = epoch;
  const [health, result] = await Promise.all([api("/api/status"),api(`/api/invoices?limit=20&offset=${offset}`)]);
  if (generation !== epoch) return;
  mode = health.mode; $("mode").textContent = mode === "demo" ? "DEMO" : "WAM RPC";
  $("demo-banner").hidden = mode !== "demo";
  $("node-state").textContent = health.ready ? "● Đối soát đang hoạt động" : "○ Chưa xác minh được node";
  $("sync-time").textContent = date(health.last_sync_at);
  $("rows").replaceChildren();
  $("empty").hidden = result.invoices.length > 0; $("invoice-table").hidden = result.invoices.length === 0;
  for (const inv of result.invoices) {
    const row = document.createElement("tr");
    const name = document.createElement("td"); name.textContent = inv.memo || "Hóa đơn " + inv.id.slice(0,8);
    const time = document.createElement("small"); time.textContent = date(inv.created_at); name.append(time);
    const amount = document.createElement("td"); amount.textContent = inv.amount;
    const state = document.createElement("td"); const tag = document.createElement("span"); badge(tag, inv.status, inv.fresh); state.append(tag);
    if (!inv.fresh) { const stale = document.createElement("small"); stale.textContent = "Chờ dữ liệu mới"; state.append(stale); }
    const action = document.createElement("td"); const button = document.createElement("button"); button.className = "quiet"; button.textContent = "Xem";
    button.addEventListener("click", () => show(inv.id).catch(e => notice(e.message))); action.append(button);
    row.append(name, amount, state, action); $("rows").append(row);
  }
  $("prev").disabled = offset === 0; $("next").disabled = result.invoices.length < 20; $("page").textContent = String(offset / 20 + 1);
  if (selected) await show(selected);
}
async function show(id) {
  selected = id; const generation = epoch;
  const inv = await api(`/api/invoices/${id}`);
  if (selected !== id || generation !== epoch) return;
  $("detail").hidden = false; $("detail-title").textContent = inv.memo || "Hóa đơn " + inv.id.slice(0,8);
  badge($("detail-state"), inv.status, inv.fresh); $("address").textContent = inv.address;
  $("due").textContent = inv.amount + " WAM"; $("received").textContent = inv.received + " WAM";
  $("confirmed").textContent = inv.confirmed + " WAM"; $("overpaid").textContent = inv.overpaid + " WAM";
  $("invoice-meta").textContent = `Hết hạn: ${date(inv.expires_at)} · Cần ${inv.required_confirmations} xác nhận · ID ${inv.id}`;
  $("detail-warning").textContent = !inv.fresh ? "Dữ liệu chưa được xác minh mới. Chờ node kết nối và đồng bộ." : inv.needs_review ? "Thanh toán đã bị giảm xác nhận hoặc bị loại. Cần kiểm tra thủ công trước khi xử lý đơn." : inv.status === "late_paid" ? "Đủ tiền nhưng có phần được phát hiện sau hạn. Cần quyết định thủ công." : mode === "demo" ? "Đây là kết quả mô phỏng, không phải thanh toán thật." : inv.eligible_for_fulfillment ? "Đã đạt chính sách xác nhận của hóa đơn tại lần đối soát gần nhất. Kiểm tra lại trước khi giao hàng." : "Chưa đủ điều kiện xác nhận thanh toán.";
  $("demo-controls").hidden = mode !== "demo"; $("payments").replaceChildren();
  for (const p of inv.payments) {
    const div = document.createElement("div"); div.className = "payment";
    const label = document.createElement("span"); label.textContent = `${p.amount} WAM · ${p.active ? p.confirmations + " xác nhận" : "Đã bị loại"} · vout ${p.vout}`;
    const tx = document.createElement("code"); tx.textContent = p.txid; div.append(label, tx);
    if (mode === "demo" && p.active) for (const [text, confirmations] of [["Đủ xác nhận", inv.required_confirmations],["Loại giao dịch", -1]]) {
      const button = document.createElement("button"); button.className = "quiet"; button.textContent = text;
      button.addEventListener("click", async () => { button.disabled = true; try { await post(`/api/invoices/${id}/demo-payments`, {txid:p.txid,confirmations}); await refresh(); } catch(e) { notice(e.message); button.disabled = false; } }); div.append(button);
    }
    $("payments").append(div);
  }
  if (!inv.payments.length) $("payments").textContent = "Chưa phát hiện giao dịch.";
}
$("invoice-form").addEventListener("submit", async event => {
  event.preventDefault(); $("create-button").disabled = true;
  const body = {amount:$("amount").value.trim(),memo:$("memo").value,expires_in_seconds:Number($("ttl").value)};
  const fingerprint = JSON.stringify(body);
  if (!createAttempt || createAttempt.fingerprint !== fingerprint) createAttempt = {fingerprint,key:crypto.randomUUID()};
  try { const inv = await post("/api/invoices", body, {"Idempotency-Key":createAttempt.key}); createAttempt = null; $("invoice-form").reset(); selected = inv.id; offset = 0; notice("Đã tạo hóa đơn."); await refresh(); }
  catch(e) { notice(e.message); } finally { $("create-button").disabled = false; }
});
$("demo-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.target.querySelector("button"); button.disabled = true;
  try { await post(`/api/invoices/${selected}/demo-payments`, {amount:$("demo-amount").value.trim(),confirmations:Number($("demo-confirmations").value)}); notice("Đã thêm thanh toán mô phỏng."); await refresh(); }
  catch(e) { notice(e.message); } finally { button.disabled = false; }
});
$("refresh").addEventListener("click", () => refresh().catch(e => { markStale(); notice(e.message); }));
$("prev").addEventListener("click", () => { offset = Math.max(0, offset - 20); refresh().catch(e => notice(e.message)); });
$("next").addEventListener("click", () => { offset += 20; refresh().catch(e => notice(e.message)); });
$("copy-address").addEventListener("click", async () => { try { await navigator.clipboard.writeText($("address").textContent); notice("Đã sao chép địa chỉ."); } catch { notice("Không sao chép được; anh có thể chọn địa chỉ và sao chép thủ công."); } });
