<template>
  <div class="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 py-10 px-4">
    <div class="max-w-2xl mx-auto">
      <div class="bg-white rounded-2xl shadow-xl shadow-indigo-100/50 overflow-hidden">
        <div class="bg-gradient-to-r from-indigo-500 to-purple-500 px-6 py-5">
          <h2 class="text-xl font-bold text-white">AI 音乐生成</h2>
          <p class="text-indigo-100 text-sm mt-1">MusicGen 生成音乐 · FFmpeg 合成 MV</p>
        </div>

        <div class="p-6 space-y-5">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">歌曲描述</label>
            <textarea
              v-model="prompt"
              rows="3"
              placeholder="描述歌曲风格与内容，如：欢快的电子流行歌曲，适合短视频"
              class="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none resize-none transition"
            />
          </div>

          <div class="flex items-center gap-3">
            <label class="text-sm font-medium text-gray-700">时长</label>
            <input
              v-model.number="duration"
              type="number"
              min="15"
              max="60"
              class="w-24 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <span class="text-sm text-gray-500">秒</span>
          </div>

          <div class="flex gap-3">
            <button
              :disabled="busy"
              @click="genMusic"
              class="flex-1 rounded-xl bg-indigo-600 text-white font-medium py-3 px-4 shadow-md shadow-indigo-200 hover:bg-indigo-700 hover:shadow-lg active:scale-95 transition disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-indigo-600 disabled:active:scale-100"
            >
              生成音乐
            </button>
            <button
              :disabled="busy || !musicUrl"
              @click="genMv"
              class="flex-1 rounded-xl bg-purple-600 text-white font-medium py-3 px-4 shadow-md shadow-purple-200 hover:bg-purple-700 hover:shadow-lg active:scale-95 transition disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-purple-600 disabled:active:scale-100"
            >
              生成 MV
            </button>
          </div>

          <div
            v-if="statusText"
            class="rounded-lg px-4 py-3 text-sm flex items-center gap-2"
            :class="error ? 'bg-red-50 text-red-700' : 'bg-blue-50 text-blue-700'"
          >
            <span :class="error ? '' : 'animate-pulse'">{{ statusText }}</span>
          </div>

          <div v-if="busy" class="space-y-1">
            <div class="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
              <div
                class="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500"
                :style="{ width: progress + '%' }"
              />
            </div>
            <div class="text-xs text-gray-500 text-right">{{ progress }}%</div>
          </div>

          <div v-if="musicUrl" class="rounded-xl border border-gray-200 p-4 space-y-3 bg-gray-50">
            <h3 class="text-sm font-semibold text-gray-700">音频预览</h3>
            <audio :src="absUrl(musicUrl)" controls class="w-full" />
            <a
              :href="absUrl(musicUrl)"
              download
              class="inline-block text-sm text-indigo-600 hover:text-indigo-800 hover:underline font-medium"
            >
              下载音频 ↓
            </a>
          </div>

          <div v-if="videoUrl" class="rounded-xl border border-gray-200 p-4 space-y-3 bg-gray-50">
            <h3 class="text-sm font-semibold text-gray-700">视频预览</h3>
            <video :src="absUrl(videoUrl)" controls class="w-full rounded-lg" />
            <a
              :href="absUrl(videoUrl)"
              download
              class="inline-block text-sm text-indigo-600 hover:text-indigo-800 hover:underline font-medium"
            >
              下载视频 ↓
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const BASE = import.meta.env.VITE_API_BASE_URL || ''
const prompt = ref('欢快的电子流行歌曲，适合短视频')
const duration = ref(30)
const musicUrl = ref('')
const videoUrl = ref('')
const busy = ref(false)
const progress = ref(0)
const statusText = ref('')
const error = ref(false)

const absUrl = (u) => (u && u.startsWith('http')) ? u : BASE + (u || '')

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = (data && (data.detail || data.error || data.message)) || `HTTP ${res.status}`
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return { res, data }
}

async function get(path) {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function poll(taskId, statusUrl, done) {
  while (true) {
    const t = await get(statusUrl)
    progress.value = t.progress || 0
    if (t.state === 'completed') return done(t)
    // 任务失败：直接展示后端返回的错误信息
    if (t.state === 'failed') throw new Error(t.error || '任务失败')
    await new Promise(r => setTimeout(r, 3000))
  }
}

async function genMusic() {
  busy.value = true
  error.value = false
  musicUrl.value = ''
  videoUrl.value = ''
  progress.value = 0
  try {
    statusText.value = '提交任务…'
    const { data: r } = await post('/api/v1/ai/generate', {
      prompt: prompt.value,
      duration: duration.value,
    })
    // 音乐接口：业务繁忙时 success=false，直接展示后端消息并停止轮询
    if (!r.success) {
      throw new Error(r.error || r.message || '生成失败，请稍后再试')
    }
    statusText.value = '正在生成音乐，约需 1-2 分钟…'
    const t = await poll(r.task_id, r.status_url, () => ({}))
    musicUrl.value = t.audio_url
    statusText.value = '音乐生成完成'
  } catch (e) {
    error.value = true
    // MV/任务 429 忙碌提示优先
    if (e.status === 429) {
      statusText.value = '服务器当前忙碌，请稍后再提交任务'
    } else {
      statusText.value = e.message || '出错，请稍后再试'
    }
  } finally {
    busy.value = false
  }
}

async function genMv() {
  busy.value = true
  error.value = false
  videoUrl.value = ''
  progress.value = 0
  try {
    statusText.value = '提交任务…'
    const { data: r } = await post('/api/v1/mv/render', {
      prompt: prompt.value,
      title: 'AI Music Video',
      lyrics: prompt.value,
      style: 'pop',
      duration: duration.value,
    })
    statusText.value = '正在合成 MV，约需 1-2 分钟…'
    const t = await poll(r.task_id, r.status_url, () => ({}))
    videoUrl.value = t.video_url
    statusText.value = 'MV 生成完成'
  } catch (e) {
    error.value = true
    // MV 接口 429：用户任务锁/服务器忙碌
    if (e.status === 429) {
      statusText.value = '服务器当前忙碌，请稍后再提交任务'
    } else {
      statusText.value = e.message || '出错，请稍后再试'
    }
  } finally {
    busy.value = false
  }
}
</script>