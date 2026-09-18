<script setup>
import { onMounted, ref, watch } from 'vue'
import { getJSON, postJSON } from '../api'

const accounts = ref([])
const accountId = ref(null)
const period = ref(currentMonth())
const gross = ref(null)
const peak = ref(false)
const result = ref(null)
const loading = ref(false)
const saving = ref(false)
const savedId = ref(null)
const errorMsg = ref('')
let timer = null

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

const errDetail = (e) => {
  try { return JSON.parse(e.message)?.detail || e.message } catch { return e.message }
}

onMounted(async () => {
  accounts.value = (await getJSON('/api/accounts')).items
  if (accounts.value.length) {
    // accountId 变化会触发 hydrateReading，随后自动预览
    accountId.value = accounts.value[0].id
  }
})

// 选中户号时用其最近抄表带出毛电量与尖峰默认值
async function hydrateReading() {
  if (!accountId.value) return
  const d = await getJSON(`/api/accounts/${accountId.value}`)
  const r = d.readings?.[0]
  gross.value = r ? r.kwh : null
  peak.value = r ? !!r.peak : false
}

watch(accountId, hydrateReading)
watch([accountId, period, gross, peak], schedulePreview)

function schedulePreview() {
  clearTimeout(timer)
  timer = setTimeout(runPreview, 280)
}

async function runPreview() {
  result.value = null
  savedId.value = null
  errorMsg.value = ''
  if (!accountId.value || !period.value || gross.value === null || Number(gross.value) < 0) return
  loading.value = true
  try {
    result.value = await postJSON('/api/solar-offsets/preview', {
      account_id: accountId.value,
      billing_period: period.value,
      gross_kwh: Number(gross.value),
      peak: peak.value,
    })
  } catch (e) {
    errorMsg.value = errDetail(e)
  } finally {
    loading.value = false
  }
}

async function saveRun() {
  errorMsg.value = ''
  if (!accountId.value || !period.value || gross.value === null || Number(gross.value) < 0) return
  saving.value = true
  try {
    const saved = await postJSON('/api/solar-offsets/runs', {
      account_id: accountId.value,
      billing_period: period.value,
      gross_kwh: Number(gross.value),
      peak: peak.value,
    })
    result.value = saved
    savedId.value = saved.run_id
  } catch (e) {
    errorMsg.value = errDetail(e)
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <div class="page work">
    <h1>测算工作台</h1>
    <div class="panel form-row">
      <label>户号
        <select v-model="accountId">
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}（{{ a.meter_no }}）</option>
        </select>
      </label>
      <label>账期 <input type="month" v-model="period" /></label>
      <label>毛电量(kWh) <input type="number" v-model.number="gross" min="0" step="0.001" /></label>
      <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
      <button :disabled="!result || saving" @click="saveRun">保存运行</button>
    </div>
    <p class="muted" style="margin-top:-0.4rem">预览不落库、不写运行记录；选择户号与账期后自动带出该账期有效抵扣。保存运行会记下当前测算。</p>
    <p v-if="savedId" class="ok">已保存为运行 #{{ savedId }}</p>
    <p v-if="errorMsg" class="err">{{ errorMsg }}</p>

    <div v-if="result" class="panel">
      <div class="offset-line">
        <template v-if="result.offset_record">
          已带出抵扣 <strong>v{{ result.offset_record.version }}</strong>
          · 录入 {{ result.offset_record.offset_kwh }} kWh
          <span v-if="result.offset_record.entered_by" class="muted">· {{ result.offset_record.entered_by }}</span>
          <span v-if="result.offset_record.source_note" class="muted">· {{ result.offset_record.source_note }}</span>
        </template>
        <span v-else class="muted">该账期暂无有效抵扣，按毛电量全额计费</span>
        <span v-if="result.offset_clipped" class="warn">（抵扣超过毛电量，净电量按 0 计）</span>
      </div>

      <div class="compare">
        <div class="tile tile-gross">
          <div class="tile-label">毛电量 / 全额</div>
          <div class="tile-kwh">{{ result.gross_kwh }} kWh</div>
          <div class="tile-money">¥{{ result.gross_total }}</div>
        </div>
        <div class="tile tile-offset">
          <div class="tile-label">光伏抵扣</div>
          <div class="tile-kwh">−{{ result.offset_kwh }} kWh</div>
          <div class="tile-money saving">省 ¥{{ result.saving }}</div>
        </div>
        <div class="tile tile-net">
          <div class="tile-label">净电量 / 应付</div>
          <div class="tile-kwh">{{ result.net_kwh }} kWh</div>
          <div class="tile-money">¥{{ result.total }}</div>
        </div>
      </div>

      <h3>净电量分段明细</h3>
      <table v-if="result.segments.length">
        <thead>
          <tr><th>净电量区间(kWh)</th><th>电量</th><th>阶梯原价</th><th>尖峰系数</th><th>结算单价</th><th>金额</th></tr>
        </thead>
        <tbody>
          <tr v-for="(s, i) in result.segments" :key="i">
            <td>{{ s.from_kwh }} – {{ s.to_kwh }}</td>
            <td>{{ s.qty }}</td>
            <td>¥{{ s.base_price }}</td>
            <td>×{{ s.peak_factor }}</td>
            <td>¥{{ s.price }}</td>
            <td>¥{{ s.amount }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">净电量为 0，无分段金额</p>
    </div>
    <p v-else-if="loading" class="muted">测算中…</p>
  </div>
</template>
<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }
input[type=number], input[type=month] { width: 9rem; margin-left: 0.35rem; }
select { margin-left: 0.35rem; }
.err { color: #ff8a8a; }
.ok { color: var(--accent); }
.warn { color: #e8c25a; }
.offset-line { margin-bottom: 0.9rem; }
.compare { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.8rem; margin-bottom: 1rem; }
.tile { border-radius: 10px; padding: 0.9rem 1rem; }
.tile-label { font-size: 0.82rem; color: var(--muted); margin-bottom: 0.3rem; }
.tile-kwh { font-size: 1.25rem; font-weight: 700; }
.tile-money { font-size: 1.5rem; font-weight: 700; margin-top: 0.25rem; }
.tile-gross { background: color-mix(in srgb, var(--muted) 16%, var(--panel)); }
.tile-offset { background: color-mix(in srgb, #5aa9ff 18%, var(--panel)); }
.tile-net { background: color-mix(in srgb, var(--accent) 22%, var(--panel)); }
.tile-net .tile-money { color: var(--accent); }
.saving { color: #7cc0ff; font-size: 1.15rem; }
</style>
