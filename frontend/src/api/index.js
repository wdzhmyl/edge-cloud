import axios from 'axios'

// 开发环境经 Vite 代理转发到 FastAPI（:8000）；生产由 FastAPI 直接伺服
// 注意：本模块不静态 import stores/auth（避免循环引用），401 处理内动态加载
const api = axios.create({ baseURL: '/api', timeout: 120000 })

// 自动带上登录 token（直接读 localStorage，与 store 双向同步）
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // 记录该请求使用的 token，供 401 时比对（避免误清刚登录的新 token）
  config._token = token
  return config
})

// 401 时清理登录态并跳回前导页（仅当失败请求用的就是当前 token，防止竞态误清）
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const cur = localStorage.getItem('token')
    if (err.response?.status === 401 && err.config?._token && err.config._token === cur) {
      const { useAuth } = await import('../stores/auth')
      useAuth().clearAuth()
      const router = (await import('../router')).default
      if (router.currentRoute.value.path !== '/') {
        router.push('/')
      }
    }
    return Promise.reject(err)
  }
)

// ===== 巡检 / 监控（原有）=====
export const getHealth = () => api.get('/health')

export const inspect = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/inspect', fd, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const getCameras = () => api.get('/cameras')

export const addNetCam = (url) => api.post('/cameras/net', { url })

export const startMonitor = (source) => api.post('/monitor/start', { source })

export const stopMonitor = () => api.post('/monitor/stop')

export const getState = () => api.get('/monitor/state')

export const screenshot = () => api.post('/monitor/screenshot')

// 浏览器摄像头模式：送帧检测 / 合成截屏入库
export const postFrame = (b64) => api.post('/monitor/frame', { image: b64 })

export const webcamShot = (blob) => {
  const fd = new FormData()
  fd.append('file', blob, 'webcam_shot.jpg')
  return api.post('/monitor/shot', fd, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const getReport = () => api.get('/monitor/report')

export const getGallery = () => api.get('/monitor/gallery')

export const streamUrl = '/api/monitor/stream'

// ===== 认证 =====
export const register = (username, password, nickname) =>
  api.post('/auth/register', { username, password, nickname })

export const login = (username, password) => api.post('/auth/login', { username, password })

export const logout = () => api.post('/auth/logout')

export const getMe = () => api.get('/me')

export const updateMe = (profile) => api.put('/me', profile)

// 危险作业区（支持多个）：列表 / 新增 / 删单个 / 清空
export const getZones = () => api.get('/me/zones')

export const saveZone = (zone) => api.post('/me/zones', { zone })

export const deleteZone = (id) => api.delete(`/me/zones/${id}`)

export const clearZones = () => api.delete('/me/zones')

export const uploadAvatar = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/me/avatar', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}

// ===== 相册（多级嵌套）=====
export const getAlbums = (parentId = 0) => api.get('/albums', { params: { parent_id: parentId } })

export const getAlbumsTree = () => api.get('/albums/tree')

export const getMoveTargets = () => api.get('/albums/move-targets')

export const createAlbum = (name, parentId = 0) => api.post('/albums', { name, parent_id: parentId })

export const deleteAlbum = (id) => api.delete(`/albums/${id}`)

export const getPhotos = (albumId) => api.get(`/albums/${albumId}/photos`)

export const uploadPhoto = (albumId, file, note) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('note', note || '')
  return api.post(`/albums/${albumId}/photos`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// ===== 共享文件夹（多级嵌套）=====
export const getShared = (parentId = 0) => api.get('/shared', { params: { parent_id: parentId } })

export const createSharedFolder = (name, parentId = 0) =>
  api.post('/shared/folders', { name, parent_id: parentId })

export const uploadSharedPhoto = (file, note, albumId = 0) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('note', note || '')
  if (albumId) fd.append('album_id', albumId)
  return api.post('/shared/photos', fd, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// ===== 管理员：用户管理 =====
export const adminUsers = () => api.get('/admin/users')

export const adminDeleteUser = (id) => api.delete(`/admin/users/${id}`)

export const adminSetRole = (id, role) => api.put(`/admin/users/${id}/role`, { role })

export const deletePhoto = (id) => api.delete(`/photos/${id}`)

export const movePhoto = (id, albumId) => api.put(`/photos/${id}/move`, { album_id: albumId })

// 对相册中已有照片巡检（复用原图，结果落库）
export const inspectPhotoById = (id) => api.post(`/photos/${id}/inspect`)

// 获取某照片的巡检结果（悬浮展示用，无结果 404）
export const getInspection = (id) => api.get(`/photos/${id}/inspection`)

// 批量操作
export const batchMovePhotos = (ids, albumId) => api.post('/photos/batch-move', { ids, album_id: albumId })

export const batchDeletePhotos = (ids) => api.post('/photos/batch-delete', { ids })

// 浏览器 <img> 标签带不了 Authorization 头，用 ?token= 查询参数
export const photoUrl = (id) => `/api/photos/${id}/file?token=${localStorage.getItem('token') || ''}`

// 头像地址（user.avatar 形如 /api/me/avatar?v=...，追加 token）
export const avatarSrc = (user) =>
  user?.avatar ? `${user.avatar}&token=${localStorage.getItem('token') || ''}` : ''
