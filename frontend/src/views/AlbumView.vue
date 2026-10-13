<template>
  <div class="album-view">
    <!-- 个人根目录视图 -->
    <template v-if="nav.mode === 'root'">
      <div class="page-head">
        <h2>我的相册</h2>
        <el-button type="primary" :icon="Plus" round @click="newDialog = true">新建文件夹</el-button>
      </div>
      <div class="album-grid">
        <!-- 共享文件夹（置顶入口） -->
        <div class="album-card shared" @click="openShared">
          <div class="cover shared-cover">
            <el-icon :size="30"><Share /></el-icon>
          </div>
          <div class="meta">
            <span class="name">共享文件夹</span>
            <span class="count">所有账号可见</span>
          </div>
        </div>
        <!-- 个人根级文件夹 -->
        <div
          v-for="a in folders"
          :key="a.id"
          class="album-card"
          @click="enterFolder(a)"
        >
          <div class="cover">
            <img v-if="a.cover_id" :src="photoUrl(a.cover_id)" alt="" />
            <div v-else class="cover-empty">
              <el-icon :size="30"><FolderOpened v-if="a.sub_count" /><Folder v-else /></el-icon>
              <span v-if="a.sub_count" class="sub-badge">{{ a.sub_count }} 子目录</span>
            </div>
            <el-button class="del" type="danger" size="small" circle :icon="Delete"
              @click.stop="removeAlbum(a)" />
          </div>
          <div class="meta">
            <span class="name">{{ a.name }}</span>
            <span class="count">{{ a.count }} 张</span>
          </div>
        </div>
        <el-empty v-if="!folders.length" description="还没有文件夹，点右上角新建；监控截图会自动归入「巡检截图」" />
      </div>
    </template>

    <!-- 文件夹内部（个人子目录 / 共享目录） -->
    <template v-else>
      <div class="page-head">
        <div class="crumb">
          <el-button :icon="Back" text @click="backToRoot">我的相册</el-button>
          <template v-for="(t, i) in trail" :key="t.id">
            <span class="sep">/</span>
            <span
              class="crumb-item"
              :class="{ active: i === trail.length - 1 }"
              @click="gotoTrail(i)"
            >{{ t.name }}</span>
          </template>
          <el-tag v-if="nav.shared" type="warning" size="small" style="margin-left: 8px">共享</el-tag>
        </div>
        <div class="head-ops">
          <el-button v-if="!selectMode" round @click="newDialog = true">新建子文件夹</el-button>
          <el-button v-if="!selectMode" round @click="enterSelect">多选</el-button>
          <template v-else>
            <el-button round @click="toggleSelectAll">{{ allSelected ? '取消全选' : '全选' }}</el-button>
            <el-button type="primary" round :disabled="!selectedIds.length" @click="openBatchMove">批量移动</el-button>
            <el-button type="danger" round :disabled="!selectedIds.length" @click="batchDelete">批量删除</el-button>
            <el-button round @click="exitSelect">退出多选</el-button>
          </template>
          <el-upload :show-file-list="false" :before-upload="onUpload" accept="image/*">
            <el-button type="primary" :icon="Upload" round>上传图片</el-button>
          </el-upload>
        </div>
      </div>

      <!-- 子文件夹 -->
      <div v-if="folders.length" class="subfolders">
        <div
          v-for="a in folders"
          :key="a.id"
          class="subfolder"
          @click="enterFolder(a)"
        >
          <el-icon :size="20"><FolderOpened v-if="a.sub_count" /><Folder v-else /></el-icon>
          <span class="sf-name">{{ a.name }}</span>
          <span class="sf-count">{{ a.count }} 张<span v-if="a.sub_count"> · {{ a.sub_count }} 目录</span></span>
          <el-button class="sf-del" type="danger" size="small" circle :icon="Delete"
            @click.stop="removeAlbum(a)" />
        </div>
      </div>

      <!-- 多选提示 -->
      <div v-if="selectMode && selectedIds.length" class="select-bar">
        已选 {{ selectedIds.length }} 张
        <span v-if="nav.shared" class="select-tip">（共享文件夹内仅可管理自己上传的图片）</span>
      </div>

      <!-- 照片 -->
      <div class="photo-grid">
        <div
          v-for="p in photos"
          :key="p.id"
          class="photo-item"
          :class="{ selected: selectedIds.includes(p.id) }"
          @click="selectMode && p.can_delete && toggleSelect(p.id)"
        >
          <el-popover
            placement="right-start"
            trigger="hover"
            :width="340"
            :disabled="!p.inspected"
            @show="onHover(p)"
          >
            <template #reference>
              <div class="photo-inner">
                <div v-if="selectMode" class="select-mask">
                  <el-checkbox :model-value="selectedIds.includes(p.id)" :disabled="!p.can_delete" />
                </div>
                <span v-if="p.inspected" class="inspected-badge" title="已巡检（悬浮查看结果）">
                  <el-icon><CircleCheck /></el-icon>
                </span>
                <el-image :src="photoUrl(p.id)" fit="cover" class="img" :preview-src-list="previewList" preview-teleported />
                <div class="photo-bar">
                  <span class="time" :title="p.note">
                    {{ p.created_at }}
                    <template v-if="nav.shared"> · {{ p.uploader_name }}</template>
                    <template v-if="p.note"> · {{ p.note }}</template>
                  </span>
                  <span v-if="!selectMode" class="photo-ops" @click.stop>
                    <el-button size="small" text :icon="Search" title="巡检这张图片" @click="inspectPhoto(p)" />
                    <el-button v-if="p.can_delete" size="small" text :icon="FolderAdd" title="移动" @click="openMove(p)" />
                    <el-button v-if="p.can_delete" type="danger" size="small" text :icon="Delete" title="删除" @click="removePhoto(p)" />
                  </span>
                </div>
              </div>
            </template>
            <div class="insp-pop">
              <div v-if="inspLoading(p)" class="muted">加载巡检结果…</div>
              <template v-else-if="insp(p).report">
                <el-image v-if="insp(p).image" :src="insp(p).image" fit="contain" class="insp-img" />
                <div class="insp-counts">
                  <el-tag v-for="(v, k) in insp(p).counts" :key="k" size="small">{{ k }}：{{ v }}</el-tag>
                </div>
                <el-alert
                  v-if="insp(p).intrusion_count > 0"
                  :title="`⚠️ 危险作业区闯入 ${insp(p).intrusion_count} 起`"
                  type="error" :closable="false" class="insp-alert"
                />
                <div class="insp-report pre-wrap">{{ insp(p).report }}</div>
                <div class="muted insp-time">巡检时间：{{ insp(p).created_at }}</div>
              </template>
              <div v-else class="muted">该照片尚未巡检</div>
            </div>
          </el-popover>
        </div>
      </div>
      <el-empty v-if="!photos.length && !folders.length" description="这个目录还是空的，上传图片或在监控页截屏都会收到这里" />
    </template>

    <!-- 新建文件夹对话框 -->
    <el-dialog v-model="newDialog" :title="nav.mode === 'root' ? '新建文件夹' : '新建子文件夹'" width="360px" @closed="newName = ''">
      <el-input v-model="newName" placeholder="文件夹名称，如：夜班巡检" maxlength="20" />
      <template #footer>
        <el-button @click="newDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!newName.trim()" :loading="saving" @click="createNew">创建</el-button>
      </template>
    </el-dialog>

    <!-- 移动对话框（单张 / 批量共用） -->
    <el-dialog v-model="moveDialog" :title="batchMode ? '批量移动到文件夹' : '移动到文件夹'" width="360px">
      <el-select v-model="moveTarget" placeholder="选择目标文件夹（含共享文件夹）" class="move-select">
        <el-option v-for="a in moveTargets" :key="a.id" :label="a.label" :value="a.id" />
      </el-select>
      <template #footer>
        <el-button @click="moveDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!moveTarget" :loading="saving" @click="doMove">移动</el-button>
      </template>
    </el-dialog>

    <!-- 图片巡检结果 -->
    <el-dialog v-model="inspectDialog" title="图片巡检结果" width="70%" top="6vh">
      <div v-if="inspectResult" class="inspect-result">
        <div class="inspect-img-wrap">
          <el-image v-if="inspectResult.image" :src="inspectResult.image" fit="contain" class="inspect-img" />
        </div>
        <div class="inspect-side">
          <div class="inspect-counts">
            <el-tag v-for="(v, k) in inspectResult.counts" :key="k" size="large" style="margin: 0 6px 6px 0">
              {{ k }}：{{ v }}
            </el-tag>
            <span v-if="!Object.keys(inspectResult.counts || {}).length" class="muted">未检测到目标</span>
          </div>
          <el-alert
            v-if="inspectResult.intrusion_count > 0"
            :title="`危险作业区闯入 ${inspectResult.intrusion_count} 起：${(inspectResult.intrusion_labels || []).join('、')}`"
            type="error" show-icon :closable="false" class="inspect-alert"
          />
          <div class="inspect-report pre-wrap" v-if="inspectResult.report">{{ inspectResult.report }}</div>
          <div v-else class="muted">
            {{ inspectResult.processing ? 'AI 研判报告生成中，请稍候（云端模型响应较慢，最长约 2 分钟）…' : '暂无报告' }}
          </div>
        </div>
      </div>
      <div v-else class="muted">正在巡检...</div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Folder, FolderOpened, Delete, Back, Upload, FolderAdd, Search, Share, CircleCheck
} from '@element-plus/icons-vue'
import {
  getAlbums, getMoveTargets, createAlbum, deleteAlbum,
  getPhotos, uploadPhoto, deletePhoto, movePhoto, photoUrl,
  inspectPhotoById, getInspection,
  batchMovePhotos, batchDeletePhotos,
  getShared, createSharedFolder, uploadSharedPhoto
} from '../api'

const nav = ref({ mode: 'root', id: null, shared: false })  // root = 个人根目录
const trail = ref([])            // 面包屑（当前路径）
const folders = ref([])
const photos = ref([])
const loading = ref(false)
const saving = ref(false)
const newDialog = ref(false)
const newName = ref('')
const moveDialog = ref(false)
const moveTarget = ref('')
const moveTargets = ref([])
const sharedRootId = ref(null)
const movingPhoto = ref(null)
const inspectDialog = ref(false)
const inspectResult = ref(null)
const selectMode = ref(false)
const selectedIds = ref([])
const batchMode = ref(false)
const previewList = ref([])
const inspMap = reactive({})        // 照片巡检结果缓存 {photoId: {...}}
const inspLoadingMap = reactive({}) // 悬浮加载中标记

const allSelected = computed(() =>
  photos.value.length > 0 && selectedIds.value.length === photos.value.length)

function insp(p) { return inspMap[p.id] || {} }
function inspLoading(p) { return inspLoadingMap[p.id] || false }
async function onHover(p) {
  if (!p.inspected || inspMap[p.id] || inspLoadingMap[p.id]) return
  inspLoadingMap[p.id] = true
  try {
    const { data } = await getInspection(p.id)
    inspMap[p.id] = data
  } catch {
    inspMap[p.id] = {}
  } finally {
    inspLoadingMap[p.id] = false
  }
}

/* ============ 导航 ============ */
async function loadRoot() {
  nav.value = { mode: 'root', id: null, shared: false }
  trail.value = []
  folders.value = []
  photos.value = []
  try {
    const { data } = await getAlbums(0)
    folders.value = data.items
  } catch (e) {
    ElMessage.error('加载相册失败：' + (e.response?.data?.detail || e.message))
  }
}

async function openShared() {
  try {
    const { data } = await getShared(0)
    sharedRootId.value = data.album.id
    nav.value = { mode: 'folder', id: data.album.id, shared: true }
    trail.value = [{ id: data.album.id, name: data.album.name, shared: true }]
    folders.value = data.children
    photos.value = data.photos
    previewList.value = data.photos.map((p) => photoUrl(p.id))
  } catch (e) {
    ElMessage.error('打开共享文件夹失败：' + (e.response?.data?.detail || e.message))
  }
}

async function enterFolder(a) {
  trail.value.push({ id: a.id, name: a.name, shared: a.shared })
  nav.value = { mode: 'folder', id: a.id, shared: a.shared }
  await loadFolder()
}

async function gotoTrail(i) {
  trail.value = trail.value.slice(0, i + 1)
  const t = trail.value[i]
  nav.value = { mode: 'folder', id: t.id, shared: t.shared }
  await loadFolder()
}

function backToRoot() {
  loadRoot()
}

async function loadFolder() {
  const id = nav.value.id
  try {
    if (nav.value.shared) {
      const { data } = await getShared(id)
      folders.value = data.children
      photos.value = data.photos
    } else {
      const [fa, fp] = await Promise.all([getAlbums(id), getPhotos(id)])
      folders.value = fa.data.items
      photos.value = fp.data.items
    }
    previewList.value = photos.value.map((p) => photoUrl(p.id))
  } catch (e) {
    ElMessage.error('加载目录失败：' + (e.response?.data?.detail || e.message))
  }
}

async function reload() {
  if (nav.value.mode === 'root') await loadRoot()
  else await loadFolder()
  try {
    const { data } = await getMoveTargets()
    moveTargets.value = data.items
  } catch { /* ignore */ }
}

/* ============ 文件夹操作 ============ */
async function createNew() {
  if (!newName.value.trim()) return
  saving.value = true
  try {
    const parent = nav.value.mode === 'root' ? 0 : nav.value.id
    if (nav.value.shared) {
      await createSharedFolder(newName.value.trim(), parent)
    } else {
      await createAlbum(newName.value.trim(), parent)
    }
    newDialog.value = false
    ElMessage.success('文件夹已创建')
    await reload()
  } catch (e) {
    ElMessage.error('创建失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function removeAlbum(a) {
  try {
    await ElMessageBox.confirm(`删除文件夹「${a.name}」及其所有子文件夹和照片？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteAlbum(a.id)
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

/* ============ 上传 ============ */
async function onUpload(file) {
  try {
    if (nav.value.shared) {
      await uploadSharedPhoto(file, file.name, nav.value.id)
    } else {
      await uploadPhoto(nav.value.id, file, file.name)
    }
    ElMessage.success('上传成功')
    await reload()
  } catch (e) {
    ElMessage.error('上传失败：' + (e.response?.data?.detail || e.message))
  }
  return false
}

/* ============ 照片操作 ============ */
async function removePhoto(p) {
  try {
    await ElMessageBox.confirm('确认删除这张照片？', '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deletePhoto(p.id)
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

function openMove(p) {
  movingPhoto.value = p
  batchMode.value = false
  moveTarget.value = ''
  loadMoveTargets()
  moveDialog.value = true
}

async function loadMoveTargets() {
  try {
    const { data } = await getMoveTargets()
    moveTargets.value = data.items
  } catch { moveTargets.value = [] }
}

/* ============ 多选批量 ============ */
function enterSelect() {
  selectMode.value = true
  selectedIds.value = []
}
function exitSelect() {
  selectMode.value = false
  selectedIds.value = []
}
function toggleSelect(id) {
  const i = selectedIds.value.indexOf(id)
  if (i >= 0) selectedIds.value.splice(i, 1)
  else selectedIds.value.push(id)
}
function toggleSelectAll() {
  const selectable = photos.value.filter((p) => p.can_delete).map((p) => p.id)
  selectedIds.value = allSelected.value ? [] : [...selectable]
}
function openBatchMove() {
  batchMode.value = true
  moveTarget.value = ''
  loadMoveTargets()
  moveDialog.value = true
}
async function batchDelete() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 张照片？`, '批量删除', { type: 'warning' })
  } catch { return }
  try {
    const { data } = await batchDeletePhotos(selectedIds.value)
    ElMessage.success(`已删除 ${data.deleted} 张`)
    selectedIds.value = []
    await reload()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}
async function doMove() {
  if (!moveTarget.value) return
  saving.value = true
  try {
    if (batchMode.value) {
      if (!selectedIds.value.length) return
      const { data } = await batchMovePhotos(selectedIds.value, moveTarget.value)
      ElMessage.success(`已移动 ${data.moved} 张`)
      selectedIds.value = []
      exitSelect()
    } else {
      if (!movingPhoto.value) return
      await movePhoto(movingPhoto.value.id, moveTarget.value)
      ElMessage.success('已移动')
    }
    moveDialog.value = false
    await reload()
  } catch (e) {
    ElMessage.error('移动失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function inspectPhoto(p) {
  inspectResult.value = null
  inspectDialog.value = true
  try {
    const { data } = await inspectPhotoById(p.id)
    inspectResult.value = data
    if (data.processing && data.photo_id) {
      pollPhotoReport(p, data.photo_id)
    } else {
      inspMap[p.id] = data
      await reload()
    }
  } catch (e) {
    inspectDialog.value = false
    ElMessage.error('巡检失败：' + (e.response?.data?.detail || e.message))
  }
}

let photoPollTimer = null
function pollPhotoReport(p, pid) {
  if (photoPollTimer) clearInterval(photoPollTimer)
  photoPollTimer = setInterval(async () => {
    try {
      const { data } = await getInspection(pid)
      if (data.report) {
        clearInterval(photoPollTimer); photoPollTimer = null
        inspectResult.value = { ...inspectResult.value, report: data.report, processing: false }
        inspMap[pid] = data
        await reload()               // 报告就绪，点亮"已巡检"标记
      }
    } catch { /* 404 仍在处理 */ }
  }, 2500)
  setTimeout(() => {
    if (photoPollTimer) { clearInterval(photoPollTimer); photoPollTimer = null }
  }, 180000)
}

// 页面离开时清理轮询（后台生成不受影响，结果仍会落库；悬浮时再拉取即可看到）
onBeforeUnmount(() => {
  if (photoPollTimer) { clearInterval(photoPollTimer); photoPollTimer = null }
})

onMounted(reload)
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
  flex-wrap: wrap;
  gap: 10px;
}
.page-head h2 { margin: 0; font-size: 18px; color: #1f2937; }
.crumb { display: flex; align-items: center; gap: 4px; }
.sep { color: #cbd5e1; }
.crumb-item { color: #2563eb; cursor: pointer; font-size: 14px; }
.crumb-item.active { color: #1f2937; cursor: default; font-weight: 600; }

.album-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
}
.album-card {
  background: #fff; border-radius: 14px; overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08); cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.album-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12); }
.album-card.shared .cover { background: linear-gradient(135deg, #f59e0b, #f97316); color: #fff; }
.shared-cover { display: grid; place-items: center; }
.cover { position: relative; height: 120px; background: #e2e8f0; }
.cover img { width: 100%; height: 100%; object-fit: cover; }
.cover-empty {
  display: grid; place-items: center; height: 100%; color: #94a3b8; position: relative;
}
.sub-badge {
  position: absolute; bottom: 6px; left: 6px; font-size: 11px;
  background: rgba(0,0,0,.35); color: #fff; padding: 1px 6px; border-radius: 6px;
}
.del { position: absolute; top: 8px; right: 8px; opacity: 0; transition: opacity 0.2s; }
.album-card:hover .del { opacity: 1; }
.meta { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; }
.name { font-size: 14px; font-weight: 600; color: #1f2937; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.count { font-size: 12px; color: #94a3b8; flex-shrink: 0; }

.head-ops { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.select-bar { margin-bottom: 12px; font-size: 13px; color: var(--accent, #2563eb); }
.select-tip { color: #94a3b8; margin-left: 8px; font-size: 12px; }

.subfolders { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; margin-bottom: 18px; }
.subfolder {
  display: flex; align-items: center; gap: 10px; background: #fff; padding: 10px 14px;
  border-radius: 10px; box-shadow: 0 1px 3px rgba(15,23,42,.06); cursor: pointer; position: relative;
}
.subfolder:hover { background: #f8fafc; }
.sf-name { font-size: 14px; font-weight: 600; color: #1f2937; }
.sf-count { font-size: 12px; color: #94a3b8; margin-left: auto; }
.sf-del { position: absolute; right: 8px; top: 8px; opacity: 0; }
.subfolder:hover .sf-del { opacity: 1; }

.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}
.photo-item {
  position: relative; background: #fff; border-radius: 12px; overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08); cursor: default;
}
.photo-item.selected { outline: 2px solid var(--accent, #2563eb); }
.photo-inner { position: relative; }
.select-mask { position: absolute; top: 6px; left: 6px; z-index: 2; }
.inspected-badge {
  position: absolute; top: 6px; right: 6px; z-index: 3; color: #16a34a;
  background: rgba(255,255,255,.9); border-radius: 50%; font-size: 16px; line-height: 1;
}
.img { width: 100%; height: 150px; display: block; }
.photo-bar { display: flex; align-items: center; justify-content: space-between; padding: 4px 8px 4px 10px; }
.time { font-size: 11px; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.photo-ops { display: flex; flex-shrink: 0; }
.insp-pop { font-size: 13px; }
.insp-img { width: 100%; max-height: 240px; border-radius: 6px; margin-bottom: 8px; background: #f1f5f9; }
.insp-counts { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.insp-alert { margin-bottom: 6px; }
.insp-report { line-height: 1.7; color: #1f2937; white-space: pre-wrap; word-break: break-word; }
.insp-time { margin-top: 6px; font-size: 11px; }
.move-select { width: 100%; }

.inspect-result { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.inspect-img-wrap { background: #f1f5f9; border-radius: 8px; display: grid; place-items: center; min-height: 320px; }
.inspect-img { max-width: 100%; max-height: 420px; }
.inspect-side { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.inspect-counts { display: flex; flex-wrap: wrap; }
.inspect-report { font-size: 13px; line-height: 1.8; color: #1f2937; max-height: 380px; overflow-y: auto; }
.muted { color: #94a3b8; font-size: 13px; }
.pre-wrap { white-space: pre-wrap; word-break: break-word; }
@media (max-width: 900px) { .inspect-result { grid-template-columns: 1fr; } }
</style>
