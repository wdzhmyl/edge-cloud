<template>
  <div class="profile-view">
    <el-card class="card">
      <template #header><span>个人中心</span></template>

      <div class="avatar-row">
        <el-upload
          class="avatar-uploader"
          :show-file-list="false"
          :before-upload="onAvatar"
          accept="image/*"
        >
          <div class="avatar-wrap">
            <el-avatar :size="84" :src="avatarSrc(state.user)">
              {{ (form.nickname || 'U')[0] }}
            </el-avatar>
            <div class="avatar-mask"><el-icon><Camera /></el-icon><span>更换</span></div>
          </div>
        </el-upload>
        <div class="avatar-info">
          <div class="username">{{ form.username }}</div>
          <div class="joined">注册于 {{ form.created_at }}</div>
        </div>
      </div>

      <el-form :model="form" label-width="72px" class="form">
        <el-form-item label="昵称">
          <el-input v-model="form.nickname" maxlength="20" placeholder="展示昵称" />
        </el-form-item>
        <el-form-item label="个性签名">
          <el-input v-model="form.bio" type="textarea" :rows="2" maxlength="60" placeholder="一句话介绍自己" />
        </el-form-item>
        <el-form-item label="主题色">
          <div class="accents">
            <span
              v-for="c in accents"
              :key="c"
              class="accent"
              :class="{ active: form.accent === c }"
              :style="{ background: c }"
              @click="form.accent = c"
            />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">保存修改</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="card">
      <template #header><span>账号</span></template>
      <div class="account-row">
        <span>
          用户名：<b>{{ form.username }}</b>
          <el-tag v-if="isAdmin" type="danger" size="small" style="margin-left: 8px">管理员</el-tag>
          <el-tag v-else type="info" size="small" style="margin-left: 8px">普通用户</el-tag>
        </span>
        <el-button type="danger" text @click="logout">退出登录</el-button>
      </div>
      <div class="role-tip">
        <template v-if="isAdmin">
          管理员可管理全部用户账号（删除用户、设置角色），并可删除共享文件夹中任何人的图片。root 为默认管理员，不可被降级或删除，以防系统无管理员。
        </template>
        <template v-else>
          普通用户可管理自己的文件夹与照片；在共享文件夹中仅可删除/移动自己上传的图片。
        </template>
      </div>
    </el-card>

    <!-- 管理员：用户管理 -->
    <el-card v-if="isAdmin" class="card">
      <template #header><span>用户管理（管理员）</span></template>
      <el-table :data="users" size="small" style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="nickname" label="昵称" />
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="row.role === 1 ? 'danger' : 'info'" size="small">
              {{ row.role === 1 ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="170" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <template v-if="row.username === 'root'">
              <el-tag type="danger" size="small" effect="plain">默认管理员</el-tag>
            </template>
            <template v-else>
              <el-button
                size="small"
                text
                :type="row.role === 1 ? 'warning' : 'success'"
                @click="toggleRole(row)"
              >
                {{ row.role === 1 ? '降为用户' : '设为管理员' }}
              </el-button>
              <el-button size="small" text type="danger" @click="removeUser(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Camera } from '@element-plus/icons-vue'
import { useAuth } from '../stores/auth'
import { updateMe, uploadAvatar, avatarSrc, logout as apiLogout,
         adminUsers, adminDeleteUser, adminSetRole } from '../api'

const router = useRouter()
const { state, setAuth, clearAuth } = useAuth()
const saving = ref(false)
const users = ref([])
const isAdmin = computed(() => state.user?.role === 1)

const accents = ['#2563eb', '#7c3aed', '#059669', '#ea580c', '#dc2626', '#0f172a']

const form = reactive({
  username: '', nickname: '', bio: '', avatar: '', accent: '#2563eb', created_at: ''
})

function reset() {
  const u = state.user || {}
  Object.assign(form, u)
}
reset()

/* ============ 管理员：用户管理 ============ */
async function loadUsers() {
  if (!isAdmin.value) return
  try {
    const { data } = await adminUsers()
    users.value = data.items
  } catch { /* 忽略 */ }
}
loadUsers()

async function toggleRole(row) {
  if (row.username === 'root') return
  const target = row.role === 1 ? 0 : 1
  try {
    await ElMessageBox.confirm(
      `确认将「${row.username}」${target === 1 ? '设为管理员' : '降为普通用户'}？`, '角色变更', { type: 'warning' })
  } catch { return }
  try {
    await adminSetRole(row.id, target)
    ElMessage.success('已更新')
    await loadUsers()
  } catch (e) {
    ElMessage.error('操作失败：' + (e.response?.data?.detail || e.message))
  }
}

async function removeUser(row) {
  if (row.username === 'root') return
  try {
    await ElMessageBox.confirm(
      `确认删除用户「${row.username}」？其相册、照片、危险区将一并删除！`, '删除用户', { type: 'warning' })
  } catch { return }
  try {
    await adminDeleteUser(row.id)
    ElMessage.success('已删除')
    await loadUsers()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

async function onAvatar(file) {
  try {
    const { data } = await uploadAvatar(file)
    form.avatar = data.avatar
    setAuth(state.token, { ...state.user, avatar: data.avatar })
    ElMessage.success('头像已更新')
  } catch {
    ElMessage.error('头像上传失败')
  }
  return false
}

async function save() {
  saving.value = true
  try {
    const { data } = await updateMe({
      nickname: form.nickname, bio: form.bio, accent: form.accent
    })
    setAuth(state.token, data)
    ElMessage.success('已保存')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function logout() {
  try { await apiLogout() } catch { /* 忽略 */ }
  clearAuth()
  router.push('/')
}
</script>

<style scoped>
.profile-view {
  max-width: 640px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.card {
  border-radius: 14px;
}
.avatar-row {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 20px;
}
.avatar-wrap {
  position: relative;
  border-radius: 50%;
  cursor: pointer;
}
.avatar-mask {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  gap: 2px;
  background: rgba(15, 23, 42, 0.55);
  color: #fff;
  font-size: 11px;
  opacity: 0;
  transition: opacity 0.2s;
}
.avatar-wrap:hover .avatar-mask {
  opacity: 1;
}
.username {
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
}
.joined {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}
.accents {
  display: flex;
  gap: 10px;
}
.accent {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid transparent;
  transition: transform 0.15s;
}
.accent:hover {
  transform: scale(1.12);
}
.accent.active {
  border-color: #fff;
  box-shadow: 0 0 0 2px currentColor;
}
.account-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.role-tip {
  margin-top: 10px;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.7;
}
</style>
