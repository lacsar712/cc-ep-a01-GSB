<template>
  <div class="page">
    <div>
      <h1 style="margin-bottom: 4px">数据集指纹反查</h1>
      <p class="muted" style="margin-top: 0">
        按 dataset_content_sha256 精确（64 位）或前缀（至少 7 位）反查关联的实验 Run
      </p>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <n-form-item label="dataset_content_sha256" :show-feedback="false">
        <n-input
          v-model:value="fingerprint"
          class="mono"
          clearable
          placeholder="粘贴 64 位完整指纹，或输入至少 7 位十六进制前缀"
          @keyup.enter="search"
        />
      </n-form-item>
      <div style="display: flex; align-items: center; gap: 12px; margin-top: 8px">
        <n-button type="primary" :loading="loading" @click="search">反查 Run</n-button>
        <span class="muted" style="font-size: 13px">
          当前长度 {{ fingerprint.trim().length }}，{{ matchMode }}
        </span>
      </div>
    </div>

    <div v-if="searched" class="card">
      <n-data-table :columns="columns" :data="rows" :loading="loading" :bordered="false" />
    </div>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { lookupByDatasetFingerprint } from '../api/client'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const fingerprint = ref('')
const rows = ref([])
const loading = ref(false)
const searched = ref(false)

const matchMode = computed(() => {
  const len = fingerprint.value.trim().length
  if (len === 64) return '将按完整指纹精确匹配'
  if (len >= 7) return '将按前缀匹配'
  return '至少输入 7 位前缀（或 64 位完整指纹）'
})

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
    title: 'code_commit',
    key: 'code_commit_sha',
    render(row) {
      return h('span', { class: 'mono' }, row.code_commit_sha)
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
      return h(
        'div',
        { style: 'display:flex;gap:8px;flex-wrap:wrap' },
        [
          h(NButton, { size: 'tiny', type: 'primary', onClick: () => router.push(`/runs/${row.id}`) }, { default: () => '详情' }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => router.push(`/runs/${row.id}/lineage`) }, { default: () => '血缘' }),
        ],
      )
    },
  },
]

async function search() {
  const fp = fingerprint.value.trim().toLowerCase()
  if (fp.length < 7) {
    message.warning('请输入至少 7 位十六进制前缀，或 64 位完整指纹')
    return
  }
  if (!/^[0-9a-f]+$/.test(fp)) {
    message.error('指纹只能包含十六进制字符（0-9、a-f）')
    return
  }
  loading.value = true
  searched.value = true
  try {
    rows.value = await lookupByDatasetFingerprint(fp)
    if (!rows.value.length) {
      message.info('未找到使用该数据集指纹的 Run')
    }
  } catch (e) {
    rows.value = []
    message.error(e.message || '反查失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const q = (route.query.q || '').toString().trim()
  if (q) {
    fingerprint.value = q
    search()
  }
})
</script>
