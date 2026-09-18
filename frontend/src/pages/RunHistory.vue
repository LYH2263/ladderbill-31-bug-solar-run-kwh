<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const items = ref([])
onMounted(async () => { items.value = (await getJSON('/api/history')).items })
const summary = (row) => {
  if (row.total != null) return `¥${row.total}`
  try { const r = JSON.parse(row.result_json); return r.total != null ? `¥${r.total}` : `平${r.plain_total}/尖${r.peak_total}` } catch { return '—' }
}
</script>
<template>
  <div class="page">
    <h1>运行记录</h1>
    <table>
      <thead><tr><th>#</th><th>类型</th><th>户号</th><th>电量</th><th>合计</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="h in items" :key="h.id">
          <td>{{ h.id }}</td><td>{{ h.kind }}</td><td>{{ h.account_id ?? '—' }}</td>
          <td>{{ h.meter_kwh ?? '—' }}</td>
          <td>{{ summary(h) }}</td><td class="muted">{{ h.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
