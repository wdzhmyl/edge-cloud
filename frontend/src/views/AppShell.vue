<template>
  <div class="shell">
    <header class="shell-header">
      <div class="brand" @click="$router.push('/app/inspect')">
        <span class="logo">智</span>
        <span class="brand-name">智慧工地安全巡检</span>
      </div>
      <el-menu :default-active="activeRoute" router mode="horizontal" class="nav">
        <el-menu-item index="/app/inspect">图片巡检</el-menu-item>
        <el-menu-item index="/app/monitor">实时监控</el-menu-item>
        <el-menu-item index="/app/album">相册</el-menu-item>
      </el-menu>
      <el-dropdown trigger="click" @command="onCommand">
        <div class="user">
          <el-avatar :size="32" :src="avatarSrc(user)">{{ (user.nickname || 'U')[0] }}</el-avatar>
          <span class="nickname">{{ user.nickname || user.username }}</span>
          <el-icon><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">
              <el-icon><User /></el-icon>个人中心
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </header>
    <main class="shell-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { ArrowDown, User, SwitchButton } from '@element-plus/icons-vue'
import { useAuth } from '../stores/auth'
import { useMonitor } from '../stores/monitor'
import { logout as apiLogout, avatarSrc } from '../api'

const route = useRoute()
const router = useRouter()
const { state, clearAuth } = useAuth()
const user = computed(() => state.user || {})
const activeRoute = computed(() => route.path)

// 全局监控轮询（画廊/网络模式状态），登录后常驻
const { startPolling } = useMonitor()
onMounted(startPolling)

async function onCommand(cmd) {
  if (cmd === 'profile') router.push('/app/profile')
  else if (cmd === 'logout') {
    await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' })
    try { await apiLogout() } catch { /* 忽略 */ }
    clearAuth()
    router.push('/')
  }
}
</script>

<style scoped>
.shell {
  min-height: 100vh;
  background: #f5f7fa;
}
.shell-header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 24px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
.logo {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--accent, #2563eb);
  color: #fff;
  font-weight: 700;
}
.brand-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  white-space: nowrap;
}
.nav {
  flex: 1;
  border-bottom: none;
}
.user {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 8px;
}
.user:hover {
  background: #f1f5f9;
}
.nickname {
  font-size: 14px;
  color: #334155;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.shell-main {
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px;
}
</style>
