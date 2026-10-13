import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import {
  postFrame, webcamShot, getGallery, getState,
  getCameras, addNetCam, startMonitor, stopMonitor, screenshot,
  getZones, saveZone, deleteZone, clearZones
} from '../api'

/**
 * 监控全局单例：摄像头 / 送帧 / 截屏 / 画廊 / 危险区状态。
 * 与组件解耦——切换页面不停止监控，只有手动「停止监控」才关。
 */
const state = reactive({
  mode: 'webcam',            // webcam=浏览器摄像头 / net=网络摄像头
  camOn: false,
  monitoring: false,
  starting: false,
  discovering: false,
  alert: '未开启监控',
  counts: {},
  intrusionCount: 0,
  gallery: [],
  devices: [],
  deviceId: '',
  choices: [],
  selected: '',
  netUrl: '',
  drawMode: false,
  zones: [],                 // 已保存的危险区（可多个）
  draftZone: null
})

// ---- 模块级运行时（不进响应式）----
let mediaStream = null
let video = null             // 离屏 video 元素：抓帧用，不依赖页面挂载
let overlayCanvas = null     // 可见覆盖层画布（MonitorView 挂载时注册）
let captureTimer = null
let pollTimer = null
let sending = false
let lastAutoShot = 0
let lastFrameBlob = null
let zoneStart = null

/* ============ 轮询（画廊 + 网络模式状态）============ */
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    if (!localStorage.getItem('token')) return
    try {
      const { data } = await getGallery()
      state.gallery = data.items
    } catch { /* 忽略 */ }
    try {
      const { data } = await getState()
      state.monitoring = data.monitoring
      if (state.mode === 'net') {
        state.alert = data.alert
        state.counts = data.counts
        state.intrusionCount = data.intrusion_count
      }
    } catch { /* 忽略 */ }
  }, 2000)
}

/* ============ 摄像头设备 ============ */
async function refreshDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    ElMessage.warning('当前浏览器不支持摄像头枚举（需 HTTPS 或 localhost）')
    return
  }
  state.discovering = true
  try {
    const all = await navigator.mediaDevices.enumerateDevices()
    state.devices = all
      .filter((d) => d.kind === 'videoinput')
      .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `摄像头 ${i + 1}` }))
    if (!state.devices.length) ElMessage.warning('未发现摄像头设备')
  } catch (e) {
    ElMessage.error('枚举摄像头失败：' + e.message)
  } finally {
    state.discovering = false
  }
}

async function refreshZones() {
  try {
    const { data } = await getZones()
    state.zones = data.items
  } catch { /* 忽略 */ }
}

/* ============ 浏览器摄像头 ============ */
async function startWebcam() {
  if (!navigator.mediaDevices?.getUserMedia) {
    ElMessage.error('当前浏览器不支持摄像头调用（需 HTTPS 或 localhost 环境）')
    return
  }
  state.starting = true
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: state.deviceId ? { deviceId: { exact: state.deviceId } } : true,
      audio: false
    })
    // 离屏 video 负责抓帧（组件卸载后仍在后台跑）
    video = document.createElement('video')
    video.autoplay = true
    video.muted = true
    video.playsInline = true
    video.srcObject = mediaStream
    await video.play()
    state.camOn = true
    state.alert = '监控已开启（浏览器摄像头）'
    await refreshZones()
    captureTimer = setInterval(captureLoop, 200)
    ElMessage.success('监控已开启（切到其他页面也会持续运行）')
  } catch (e) {
    ElMessage.error('无法打开摄像头：' + (e.message || e.name))
  } finally {
    state.starting = false
  }
}

function stopWebcam() {
  if (captureTimer) { clearInterval(captureTimer); captureTimer = null }
  if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null }
  if (video) { video.srcObject = null; video = null }
  state.camOn = false
  state.drawMode = false
  state.draftZone = null
  zoneStart = null
  state.alert = '未开启监控'
  state.counts = {}
  state.intrusionCount = 0
  clearOverlay()
}

async function captureLoop() {
  if (!video || !video.videoWidth || sending) return
  sending = true
  try {
    const scale = Math.min(1, 640 / video.videoWidth)
    const c = document.createElement('canvas')
    c.width = Math.round(video.videoWidth * scale)
    c.height = Math.round(video.videoHeight * scale)
    c.getContext('2d').drawImage(video, 0, 0, c.width, c.height)
    const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.7))
    lastFrameBlob = blob
    const b64 = await blobToBase64(blob)
    const { data } = await postFrame(b64)
    if (!state.drawMode) {
      drawOverlay(data)
      state.alert = buildAlert(data)
      state.counts = data.counts || {}
      state.intrusionCount = data.intrusion_count || 0
    }
    // 闯入自动截屏：5 秒防抖
    if (data.intrusion_count > 0 && Date.now() - lastAutoShot > 5000) {
      lastAutoShot = Date.now()
      const shot = await composeShot()
      if (shot) {
        try {
          await webcamShot(shot)
          refreshGallery()
        } catch { /* 自动截屏失败不影响主循环 */ }
      }
    }
  } catch { /* 单帧失败不打断循环 */ }
  finally { sending = false }
}

/* ============ 覆盖层绘制 ============ */
export function registerOverlay(canvas) { overlayCanvas = canvas }
export function unregisterOverlay() { overlayCanvas = null }

function clearOverlay() {
  if (overlayCanvas) overlayCanvas.getContext('2d').clearRect(0, 0, overlayCanvas.width, overlayCanvas.height)
}

function drawOverlay(data) {
  const ov = overlayCanvas
  const v = document.querySelector('.cam-video')
  if (!ov || !v) return
  const ctx = ov.getContext('2d')
  const rect = v.getBoundingClientRect()
  ov.width = rect.width
  ov.height = rect.height
  ctx.clearRect(0, 0, ov.width, ov.height)
  const W = ov.width, H = ov.height
  // 全部危险区（橙框）
  for (const [x1, y1, x2, y2] of data.zones || []) {
    ctx.strokeStyle = '#f59e0b'
    ctx.lineWidth = 3
    ctx.strokeRect(x1 * W, y1 * H, (x2 - x1) * W, (y2 - y1) * H)
    ctx.fillStyle = '#f59e0b'
    ctx.font = '12px sans-serif'
    ctx.fillText(data.zone_label || '危险作业区', x1 * W, Math.max(12, y1 * H - 4))
  }
  // 检测框
  for (const d of data.detections || []) {
    const [x1, y1, x2, y2] = d.box
    ctx.strokeStyle = d.in_zone ? 'red' : '#16a34a'
    ctx.lineWidth = 2
    ctx.strokeRect(x1 * W, y1 * H, (x2 - x1) * W, (y2 - y1) * H)
    ctx.fillStyle = d.in_zone ? 'red' : '#16a34a'
    ctx.font = '12px sans-serif'
    ctx.fillText(`${d.in_zone ? '⚠闯入 ' : ''}${d.label_zh} ${d.conf.toFixed(2)}`, x1 * W, Math.max(12, y1 * H - 4))
  }
}

function buildAlert(data) {
  if (!data.detections?.length) return '未检测到目标。'
  const lines = Object.entries(data.counts || {}).map(([k, v]) => `- **${k}**：${v} 个`).join('\n')
  if (data.intrusion_count > 0) {
    const names = data.detections.filter((d) => d.in_zone).map((d) => d.label_zh)
    return `${lines}\n\n**危险作业区闯入 ${data.intrusion_count} 起**（${names.join('、')}），请立即核查！`
  }
  return lines
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onloadend = () => resolve(r.result)
    r.onerror = reject
    r.readAsDataURL(blob)
  })
}

/* ============ 危险区手动划定 ============ */
function toggleDrawMode() {
  state.drawMode = !state.drawMode
  state.draftZone = null
  zoneStart = null
  if (state.drawMode) {
    clearOverlay()
    ElMessage.info('划定模式：在画面上按住拖拽框选，松开保存（可划多个）')
  }
}

function _zonePoint(e) {
  const ov = overlayCanvas
  const rect = ov.getBoundingClientRect()
  return {
    x: Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
    y: Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height))
  }
}

function onZoneDown(e) {
  if (!state.drawMode) return
  zoneStart = _zonePoint(e)
  state.draftZone = [zoneStart.x, zoneStart.y, zoneStart.x, zoneStart.y]
}

function onZoneMove(e) {
  if (!state.drawMode || !zoneStart) return
  const p = _zonePoint(e)
  state.draftZone = [zoneStart.x, zoneStart.y, p.x, p.y]
  renderDraft()
}

async function onZoneUp() {
  if (!state.drawMode || !zoneStart) return
  const [x1, y1, x2, y2] = state.draftZone || [0, 0, 0, 0]
  zoneStart = null
  state.draftZone = null
  if (x2 - x1 < 0.03 || y2 - y1 < 0.03) { renderDraft(); return }
  try {
    await saveZone([x1, y1, x2, y2])
    state.drawMode = false
    await refreshZones()
    ElMessage.success(`危险区域已保存（共 ${state.zones.length} 个）`)
  } catch (err) {
    ElMessage.error('保存失败：' + (err.response?.data?.detail || err.message))
  }
}

function renderDraft() {
  const ov = overlayCanvas
  if (!ov || !state.draftZone) return
  const ctx = ov.getContext('2d')
  const [x1, y1, x2, y2] = state.draftZone
  ctx.clearRect(0, 0, ov.width, ov.height)
  ctx.setLineDash([6, 4])
  ctx.strokeStyle = '#f59e0b'
  ctx.lineWidth = 2
  ctx.strokeRect(x1 * ov.width, y1 * ov.height, (x2 - x1) * ov.width, (y2 - y1) * ov.height)
  ctx.setLineDash([])
  ctx.fillStyle = '#f59e0b'
  ctx.font = '12px sans-serif'
  ctx.fillText('松开保存', x1 * ov.width, Math.max(12, y1 * ov.height - 4))
}

async function doDeleteZone(id) {
  try {
    await deleteZone(id)
    await refreshZones()
    ElMessage.success('已删除该危险区域')
  } catch (err) {
    ElMessage.error('删除失败：' + (err.response?.data?.detail || err.message))
  }
}

async function doClearZones() {
  try {
    await clearZones()
    await refreshZones()
    ElMessage.success('已清空全部危险区域')
  } catch (err) {
    ElMessage.error('操作失败：' + (err.response?.data?.detail || err.message))
  }
}

/* ============ 截屏 ============ */
async function composeShot() {
  if (!video || !video.videoWidth) return null
  const c = document.createElement('canvas')
  c.width = video.videoWidth
  c.height = video.videoHeight
  const ctx = c.getContext('2d')
  ctx.drawImage(video, 0, 0)
  if (overlayCanvas && overlayCanvas.width) {
    ctx.drawImage(overlayCanvas, 0, 0, c.width, c.height)
  }
  return new Promise((r) => c.toBlob(r, 'image/jpeg', 0.9))
}

async function doShot() {
  try {
    if (state.mode === 'webcam') {
      const blob = await composeShot()
      if (!blob) { ElMessage.warning('请先开启监控'); return }
      const { data } = await webcamShot(blob)
      ElMessage.success(data.message)
    } else {
      const { data } = await screenshot()
      ElMessage.success(data.message)
    }
    refreshGallery()
  } catch (e) {
    ElMessage.error('截屏失败：' + (e.response?.data?.detail || e.message))
  }
}

async function refreshGallery() {
  try {
    const { data } = await getGallery()
    state.gallery = data.items
  } catch { /* 忽略 */ }
}

/* ============ 网络摄像头模式 ============ */
async function doDiscover() {
  state.discovering = true
  try {
    const { data } = await getCameras()
    state.choices = data.choices
    state.selected = data.value || ''
    ElMessage.success(data.message)
  } catch (e) {
    ElMessage.error('搜索失败：' + (e.response?.data?.detail || e.message))
  } finally {
    state.discovering = false
  }
}

async function doAddNet() {
  if (!state.netUrl.trim()) { ElMessage.warning('请输入摄像头地址'); return }
  try {
    const { data } = await addNetCam(state.netUrl.trim())
    state.choices = data.choices
    state.selected = data.value || state.selected
    ElMessage.success(data.message)
  } catch (e) {
    ElMessage.error('添加失败：' + (e.response?.data?.detail || e.message))
  }
}

async function doStart() {
  if (!state.selected) { ElMessage.warning('请先选择摄像头'); return }
  state.starting = true
  try {
    const { data } = await startMonitor(state.selected)
    ElMessage.success(data.message)
    state.monitoring = true
    refreshGallery()
  } catch (e) {
    ElMessage.error('开启失败：' + (e.response?.data?.detail || e.message))
  } finally {
    state.starting = false
  }
}

async function doStop() {
  try {
    await stopMonitor()
    state.monitoring = false
    state.alert = '未开启监控'
    ElMessage.success('已停止监控')
  } catch (e) {
    ElMessage.error('停止失败：' + (e.response?.data?.detail || e.message))
  }
}

function onModeChange() {
  if (state.mode !== 'webcam' && state.camOn) stopWebcam()
  if (state.mode !== 'net' && state.monitoring) doStop()
}

export function useMonitor() {
  return {
    state,
    startPolling,
    refreshDevices, refreshZones, refreshGallery,
    startWebcam, stopWebcam,
    registerOverlay, unregisterOverlay,
    toggleDrawMode, onZoneDown, onZoneMove, onZoneUp,
    doDeleteZone, doClearZones,
    doShot, composeShot,
    doDiscover, doAddNet, doStart, doStop, onModeChange,
    get mediaStream() { return mediaStream }
  }
}
