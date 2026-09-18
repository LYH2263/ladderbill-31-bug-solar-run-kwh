<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const route = useRoute()
const data = ref(null)
const offsets = ref([])
const bill = ref(null)
const peak = ref(false)
const errorMsg = ref('')
const savedMsg = ref('')

// 抵扣录入表单
const period = ref('')
const offsetKwh = ref(null)
const sourceNote = ref('')
const enteredBy = ref('')

const activeByPeriod = computed(() => {
  const m = {}
  for (const o of offsets.value) if (o.active) m[o.billing_period] = o
  return m
})
// 当前输入账期的有效版本：存在即表示本次提交是“更正”，需带显式版本号
const baseVersion = computed(() => activeByPeriod.value[period.value]?.version ?? null)
const grouped = computed(() => {
  const groups = {}
  for (const o of offsets.value) {
    ;(groups[o.billing_period] ||= []).push(o)
  }
  return Object.entries(groups)
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([p, rows]) => ({ period: p, rows }))
})

const errDetail = (e) => {
  try { return JSON.parse(e.message)?.detail || e.message } catch { return e.message }
}

const load = async () => {
  errorMsg.value = ''
  data.value = await getJSON(`/api/accounts/${route.params.id}`)
  offsets.value = (await getJSON(`/api/solar-offsets/accounts/${route.params.id}`)).items
  const r = data.value.readings[0]
  bill.value = r
    ? await postJSON('/api/bill', { account_id: +route.params.id, kwh: r.kwh, peak: !!r.peak, persist: false })
    : null
}

const startCorrection = (o) => {
  period.value = o.billing_period
  offsetKwh.value = o.offset_kwh
  sourceNote.value = o.source_note ?? ''
  enteredBy.value = o.entered_by ?? ''
  savedMsg.value = ''
  errorMsg.value = ''
}

const submitOffset = async () => {
  errorMsg.value = ''
  savedMsg.value = ''
  if (!period.value) { errorMsg.value = '请选择账期'; return }
  if (offsetKwh.value === null || Number(offsetKwh.value) < 0) { errorMsg.value = '录入电量须为非负数'; return }
  const body = {
    account_id: +route.params.id,
    billing_period: period.value,
    offset_kwh: Number(offsetKwh.value),
    source_note: sourceNote.value || null,
    entered_by: enteredBy.value || null,
  }
  if (baseVersion.value !== null) body.expected_version = baseVersion.value
  try {
    const r = await postJSON('/api/solar-offsets', body)
    savedMsg.value = baseVersion.value !== null
      ? `已保存为 v${r.item.version}，旧版 v${baseVersion.value} 只读保留`
      : '已录入有效抵扣 v1'
    offsetKwh.value = null
    sourceNote.value = ''
    await load()
  } catch (e) {
    errorMsg.value = errDetail(e)
  }
}

onMounted(load)
watch(() => route.params.id, load)
const account = computed(() => data.value?.account)
const runs = computed(() => data.value?.runs || [])
</script>
<template>
  <div class="page" v-if="account">
    <h1>{{ account.name }}</h1>
    <p class="muted">表号 {{ account.meter_no }} · {{ account.note }}</p>

    <div class="panel">
      <h3>运行记录</h3>
      <table v-if="runs.length">
        <thead>
          <tr><th>运行编号</th><th>电量</th><th>合计</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id">
            <td>#{{ r.id }}</td>
            <td>{{ r.billed_kwh ?? '—' }}</td>
            <td>{{ r.total != null ? `¥${r.total}` : '—' }}</td>
            <td class="muted">{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">暂无运行记录</p>
    </div>

    <div class="panel">
      <h3>光伏抵扣录入</h3>
      <div class="form-row">
        <label>账期
          <input type="month" v-model="period" />
        </label>
        <label>录入电量(kWh)
          <input type="number" v-model.number="offsetKwh" min="0" step="0.001" />
        </label>
        <label>来源备注
          <input type="text" v-model="sourceNote" placeholder="如：屋顶光伏并网" />
        </label>
        <label>录入者
          <input type="text" v-model="enteredBy" placeholder="操作人" />
        </label>
        <button @click="submitOffset">
          {{ baseVersion !== null ? `更正（基于 v${baseVersion}）` : '录入有效抵扣' }}
        </button>
      </div>
      <p v-if="errorMsg" class="err">{{ errorMsg }}</p>
      <p v-if="savedMsg" class="ok">{{ savedMsg }}</p>
    </div>

    <div class="panel">
      <h3>抵扣账期列表</h3>
      <table v-if="grouped.length">
        <thead>
          <tr><th>账期</th><th>版本</th><th>状态</th><th>录入电量</th><th>来源备注</th><th>录入者</th><th>录入时间</th><th></th></tr>
        </thead>
        <tbody>
          <template v-for="g in grouped" :key="g.period">
            <tr v-for="o in g.rows" :key="o.id" :class="{ inactive: !o.active }">
              <td>{{ o.billing_period }}</td>
              <td>v{{ o.version }}</td>
              <td>
                <span class="badge" :class="o.active ? 'badge-on' : 'badge-off'">
                  {{ o.active ? '有效' : '历史只读' }}
                </span>
              </td>
              <td>{{ o.offset_kwh }}</td>
              <td class="muted">{{ o.source_note }}</td>
              <td>{{ o.entered_by }}</td>
              <td class="muted">{{ o.created_at }}</td>
              <td>
                <button v-if="o.active" class="btn-mini" @click="startCorrection(o)">更正</button>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <p v-else class="muted">暂无抵扣记录</p>
    </div>

    <div class="panel">
      <h3>最近抄表试算（不含抵扣）</h3>
      <label><input type="checkbox" v-model="peak" @change="bill = null" /> 尖峰</label>
      <button @click="load">刷新</button>
      <p v-if="bill">合计 <strong class="hero-num" style="font-size:1.5rem">¥{{ bill.total }}</strong></p>
      <SegmentTable :rows="bill?.segments || []" />
    </div>
  </div>
</template>
<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }
input[type=number], input[type=month] { width: 9rem; margin-left: 0.35rem; }
input[type=text] { width: 11rem; margin-left: 0.35rem; }
.btn-mini { padding: 0.2rem 0.55rem; font-size: 0.8rem; }
.inactive td { color: var(--muted); }
.badge { padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }
.badge-on { background: color-mix(in srgb, var(--accent) 25%, transparent); color: var(--accent); }
.badge-off { background: color-mix(in srgb, var(--muted) 20%, transparent); color: var(--muted); }
.err { color: #ff8a8a; margin-top: 0.6rem; }
.ok { color: var(--accent); margin-top: 0.6rem; }
</style>
