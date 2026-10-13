import { reactive } from 'vue'

// 极简认证状态：token + user，持久化在 localStorage
// 注意：本模块不静态 import api（避免循环引用），refresh() 内动态加载
const state = reactive({
  token: localStorage.getItem('token') || '',
  user: JSON.parse(localStorage.getItem('user') || 'null')
})

function setAuth(token, user) {
  state.token = token
  state.user = user
  localStorage.setItem('token', token)
  localStorage.setItem('user', JSON.stringify(user))
  applyAccent()
}

function clearAuth() {
  state.token = ''
  state.user = null
  localStorage.removeItem('token')
  localStorage.removeItem('user')
}

async function refresh() {
  if (!state.token) return null
  const { getMe } = await import('../api')
  try {
    const { data } = await getMe()
    state.user = data
    localStorage.setItem('user', JSON.stringify(data))
    applyAccent()
    return data
  } catch {
    clearAuth()
    return null
  }
}

function applyAccent() {
  const accent = state.user?.accent || '#2563eb'
  document.documentElement.style.setProperty('--accent', accent)
}

applyAccent()

export function useAuth() {
  return { state, setAuth, clearAuth, refresh }
}
