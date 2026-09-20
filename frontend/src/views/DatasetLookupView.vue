<template>
  <div class="page">
    <div>
      <h1 style="margin-bottom: 4px">数据集指纹反查</h1>
      <p class="muted" style="margin-top: 0">
        按数据集内容指纹（dataset_content_sha256）反查关联 Run，支持完整 64 位精确值或 ≥8 位十六进制前缀
      </p>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <n-form-item label="数据集指纹" :show-feedback="false">
        <n-input
          v-model:value="sha"
          class="mono"
          clearable
          placeholder="粘贴 sha256 指纹或前缀，例如 4b7b1197129c6cb0…"
          @keyup.enter="search"
        />
      </n-form-item>
      <div style="display: flex; align-items: center; gap: 12px; margin-top: 8px">
        <n-button type="primary" :loading="loading" @click="search">查询</n-button>
        <span class="muted" style="font-size: 12px">
          仅按指纹精确/前缀匹配，最少 8 位十六进制字符
        </span>
      </div>
    </div>

    <div v-if="searched" class="card">
      <p class="muted" style="margin-top: 0">
        指纹 <span class="mono">{{ lastQuery }}</span> 命中 {{ rows.length }} 条 Run
      </p>
      <n-data-table
        v-if="rows.length"
        :columns="columns"
        :data="rows"
        :loading="loading"
        :bordered="false"
      />
      <n-empty v-else description="未找到使用该数据集的 Run" />
    </div>
  </div>
</template>

<script setup>
import { h, onMounted, ref } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { lookupDatasetRuns } from '../api/client'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const sha = ref('')
const lastQuery = ref('')
const rows = ref([])
const loading = ref(false)
const searched = ref(false)

const statusMap = {
  running: { type: 'info', label: '进行中' },
  completed: { type: 'success', label: '已完成' },
  aborted: { type: 'warning', label: '已中止' },
}

const columns = [
  { title: '项目', key: 'project' },
  { title: '名称', key: 'name' },
  {
    title: '状态',
    key: 'status',
    render(row) {
      const m = statusMap[row.status] || { type: 'default', label: row.status }
      return h(NTag, { type: m.type, size: 'small' }, { default: () => m.label })
    },
  },
  {
    title: '代码提交',
    key: 'code_commit_sha',
    render(row) {
      return h('span', { class: 'mono' }, row.code_commit_sha.slice(0, 12))
    },
  },
  {
    title: '数据集指纹',
    key: 'dataset_content_sha256',
    render(row) {
      return h('span', { class: 'mono' }, `${row.dataset_content_sha256.slice(0, 12)}…`)
    },
  },
  {
    title: '启动时间',
    key: 'started_at',
    render(row) {
      return new Date(row.started_at).toLocaleString()
    },
  },
  {
    title: '操作',
    key: 'actions',
    render(row) {
      return h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, [
        h(
          NButton,
          { size: 'tiny', onClick: () => router.push(`/runs/${row.run_id}`) },
          { default: () => '详情' },
        ),
        h(
          NButton,
          { size: 'tiny', quaternary: true, onClick: () => router.push(`/runs/${row.run_id}/lineage`) },
          { default: () => '血缘' },
        ),
      ])
    },
  },
]

async function search() {
  const query = sha.value.trim().toLowerCase()
  if (!query) {
    message.warning('请输入数据集指纹')
    return
  }
  if (!/^[0-9a-f]+$/.test(query)) {
    message.error('数据集指纹仅允许十六进制字符（0-9a-f）')
    return
  }
  if (query.length < 8) {
    message.error('指纹前缀至少 8 位十六进制字符')
    return
  }
  if (query.length > 64) {
    message.error('数据集指纹最长 64 位十六进制字符')
    return
  }
  loading.value = true
  try {
    rows.value = await lookupDatasetRuns(query)
    lastQuery.value = query
    searched.value = true
  } catch (e) {
    message.error(e.message || '查询失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const preset = typeof route.query.sha === 'string' ? route.query.sha : ''
  if (preset) {
    sha.value = preset
    search()
  }
})
</script>
