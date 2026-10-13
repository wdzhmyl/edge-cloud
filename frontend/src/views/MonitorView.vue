<template>
  <div class="monitor-view">
    <!-- 摄像头来源：本机（浏览器）/ 网络（服务器） -->
    <el-card>
      <template #header>
        <span>摄像头来源</span>
        <el-tag v-if="s.camOn" type="success" size="small" style="margin-left: 8px">监控中 · 切页面不中断</el-tag>
      </template>
      <el-radio-group v-model="s.mode" size="large" @change="onModeChange">
        <el-radio-button value="webcam">本机摄像头（浏览器）</el-radio-button>
        <el-radio-button value="net">网络摄像头（手机/RTSP）</el-radio-button>
      </el-radio-group>

      <!-- 浏览器摄像头控制 -->
      <div v-if="s.mode === 'webcam'" class="controls webcam-controls">
        <el-select v-model="s.deviceId" placeholder="选择摄像头" class="source-select">
          <el-option v-for="d in s.devices" :key="d.deviceId" :label="d.label" :value="d.deviceId" />
        </el-select>
        <el-button :icon="Search" :loading="s.discovering" @click="refreshDevices">刷新</el-button>
        <el-button type="primary" :disabled="s.camOn" :loading="s.starting" @click="startWebcam">开启监控</el-button>
        <el-button type="danger" :disabled="!s.camOn" @click="stopWebcam">停止监控</el-button>
      </div>

      <!-- 网络摄像头控制（服务器端 cv2） -->
      <div v-else class="controls">
        <el-button :icon="Search" :loading="s.discovering" @click="doDiscover">搜索摄像头</el-button>
        <el-select v-model="s.selected" placeholder="选择摄像头（本地 / 手机 / 网络）" class="source-select">
          <el-option v-for="c in s.choices" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-input v-model="s.netUrl" placeholder="如 http://手机IP:8080/video 或 rtsp://..." class="net-input" />
        <el-button @click="doAddNet">添加</el-button>
        <el-button type="primary" :disabled="!s.selected" :loading="s.starting" @click="doStart">开启监控</el-button>
        <el-button type="danger" :disabled="!s.monitoring" @click="doStop">停止监控</el-button>
      </div>
      <div class="tip">
        <template v-if="s.mode === 'webcam'">
          浏览器直接调用本机摄像头（getUserMedia），画面在本机播放，服务器只做检测——云端部署也能用，切到其他页面监控持续。
        </template>
        <template v-else>
          手机摄像头：安装 IP Webcam / DroidCam 后，将地址粘贴到输入框点击「添加」。此模式由服务器拉流。
        </template>
      </div>
    </el-card>

    <el-row :gutter="16" class="main-row">
      <el-col :span="16">
        <el-card>
          <template #header><span>实时画面（边缘端逐帧检测 / 危险区预警）</span></template>

          <!-- 浏览器摄像头：原生 video + 覆盖层画框 -->
          <div v-if="s.mode === 'webcam'" class="cam-outer">
            <div v-if="!s.camOn" class="cam-placeholder">摄像头未开启</div>
            <video ref="videoEl" class="cam-video" autoplay playsinline muted></video>
            <canvas
              ref="overlayEl"
              class="cam-overlay"
              :class="{ drawing: s.drawMode }"
              @mousedown="onZoneDown"
              @mousemove="onZoneMove"
              @mouseup="onZoneUp"
              @mouseleave="onZoneUp"
            ></canvas>
          </div>

          <!-- 网络摄像头：MJPEG 服务端推流 -->
          <div v-else class="stream-box">
            <img v-if="s.monitoring" :src="streamSrc" class="stream" alt="实时监控画面" />
            <el-empty v-else description="监控未开启" :image-size="120" />
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header><span>告警与操作</span></template>
          <el-alert :title="s.alert || '未开启监控'" :type="s.intrusionCount > 0 ? 'error' : 'info'" show-icon :closable="false" class="alert" />
          <div class="counts">
            <el-tag v-for="(v, k) in s.counts" :key="k" size="default" class="count-tag">{{ k }}：{{ v }}</el-tag>
          </div>
          <div class="ops">
            <el-button :icon="Camera" :disabled="s.mode === 'webcam' ? !s.camOn : !s.monitoring" @click="doShot">
              主动截屏
            </el-button>
            <el-button
              :type="s.drawMode ? 'danger' : 'warning'"
              :icon="Aim"
              :disabled="s.mode !== 'webcam' || !s.camOn"
              @click="toggleDrawMode"
            >
              {{ s.drawMode ? '取消划定' : '划定危险区域' }}
            </el-button>
          </div>
          <div v-if="s.drawMode" class="draw-hint">
            按住鼠标拖出一个矩形框选危险作业区，松开自动保存（可划多个，旧区域保留）
          </div>

          <!-- 危险区列表：单独删除 -->
          <div v-if="s.zones.length" class="zone-list">
            <div class="zone-head">
              <span>已划定危险区（{{ s.zones.length }}）</span>
              <el-button text type="danger" size="small" @click="doClearZones">清空</el-button>
            </div>
            <div v-for="z in s.zones" :key="z.id" class="zone-item">
              <span class="zone-name">{{ z.name }}</span>
              <span class="zone-coord">[{{ z.x1.toFixed(2) }},{{ z.y1.toFixed(2) }} ~ {{ z.x2.toFixed(2) }},{{ z.y2.toFixed(2) }}]</span>
              <el-button text type="danger" size="small" :icon="Delete" @click="doDeleteZone(z.id)" />
            </div>
          </div>
        </el-card>

        <el-card class="gallery-card">
          <template #header>
            <span>实时截图预览（最新 4 张）</span>
            <span class="gallery-tip">其余全部已存入相册，不会删除</span>
          </template>
          <div class="gallery">
            <div v-for="item in previewShots" :key="item.id" class="shot">
              <el-image :src="photoUrl(item.id)" fit="cover" class="shot-img" />
              <div class="shot-meta">{{ item.created_at }} · {{ item.note }}</div>
            </div>
            <el-empty v-if="!s.gallery.length" description="暂无截图（截屏后自动收入相册）" :image-size="60" />
          </div>
          <div v-if="s.gallery.length > 4" class="gallery-more">
            仅预览最新 4 张，共 {{ s.gallery.length }} 张已存入相册 →
            <router-link to="/app/album">查看相册</router-link>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Search, Camera, Aim, Delete } from '@element-plus/icons-vue'
import { useMonitor } from '../stores/monitor'
import { streamUrl, photoUrl } from '../api'

const m = useMonitor()
const s = m.state

const videoEl = ref(null)
const overlayEl = ref(null)
const streamKey = ref(0)
const streamSrc = computed(() => `${streamUrl}?t=${streamKey.value}`)
// 监控预览只显示最新 4 张（显示上限）；所有截图都已入库相册，绝不自动删除
const previewShots = computed(() => s.gallery.slice(0, 4))

const {
  refreshDevices, refreshZones, refreshGallery,
  startWebcam, stopWebcam,
  registerOverlay, unregisterOverlay,
  toggleDrawMode, onZoneDown, onZoneMove, onZoneUp,
  doDeleteZone, doClearZones,
  doShot,
  doDiscover, doAddNet, doStart, doStop, onModeChange
} = m

/** 把全局媒体流绑定到本页可见 video（开启监控 / 切回本页时都要执行）。 */
function bindVideo() {
  if (videoEl.value && m.mediaStream) {
    videoEl.value.srcObject = m.mediaStream
    videoEl.value.play().catch(() => {})
  }
}

onMounted(() => {
  registerOverlay(overlayEl.value)
  if (s.camOn) bindVideo()
  refreshDevices()
  refreshZones()
  refreshGallery()
})

// 在本页开启监控（或从其他页面开着监控切回来）：立即把流绑到可见 video
watch(() => s.camOn, (on) => {
  if (on) bindVideo()
  else if (videoEl.value) videoEl.value.srcObject = null
})

onUnmounted(() => {
  unregisterOverlay()
})
</script>

<style scoped>
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.webcam-controls {
  margin-top: 12px;
}
.source-select { width: 220px; }
.net-input { width: 320px; }
.tip {
  margin-top: 8px;
  font-size: 12px;
  color: #94a3b8;
}
.main-row { margin-top: 16px; }

.cam-outer {
  position: relative;
  height: 480px;
  background: #0f172a;
  border-radius: 4px;
  overflow: hidden;
}
.cam-placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #64748b;
  font-size: 16px;
  letter-spacing: 2px;
  z-index: 1;
}
.cam-video {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  max-width: 100%;
  max-height: 100%;
}
.cam-overlay {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
}
.cam-overlay.drawing {
  pointer-events: auto;
  cursor: crosshair;
}
.draw-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #d97706;
}

.zone-list {
  margin-top: 14px;
  border-top: 1px dashed #e2e8f0;
  padding-top: 10px;
}
.zone-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #475569;
  margin-bottom: 6px;
}
.zone-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 3px 0;
}
.zone-name {
  color: #1f2937;
  font-weight: 600;
}
.zone-coord {
  color: #94a3b8;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stream-box {
  height: 480px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f172a;
  border-radius: 4px;
}
.stream { max-width: 100%; max-height: 480px; }
.alert { margin-bottom: 12px; }
.counts { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.ops { display: flex; gap: 8px; flex-wrap: wrap; }
.gallery-card { margin-top: 16px; }
.gallery-card :deep(.el-card__header) { display: flex; align-items: baseline; gap: 10px; }
.gallery-tip { font-size: 12px; color: #94a3b8; font-weight: 400; }
.gallery { display: flex; flex-wrap: wrap; gap: 8px; }
.gallery-more { margin-top: 8px; font-size: 12px; color: #64748b; }
.gallery-more a { color: var(--accent, #2563eb); }
.shot { width: 120px; }
.shot-img { width: 120px; height: 90px; border-radius: 4px; }
.shot-meta { font-size: 11px; color: #64748b; margin-top: 2px; word-break: break-all; }
</style>
