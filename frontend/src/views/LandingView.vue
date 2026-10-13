<template>
  <div class="landing">
    <!-- 动态背景 -->
    <div class="bg">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="grid-lines"></div>
    </div>

    <!-- 顶部 -->
    <header class="top">
      <div class="brand">
        <span class="logo">智</span>
        <span>智慧工地安全巡检平台</span>
      </div>
      <el-button round @click="focusAuth">登录 / 注册</el-button>
    </header>

    <!-- 主区 -->
    <section class="hero">
      <div class="hero-left">
        <div class="badge"><span class="dot"></span>端云协同 · 边缘 YOLO26n + 云端多模态大模型</div>
        <h1>让每一处工地隐患<br /><span class="gradient-text">都被实时看见</span></h1>
        <p class="sub">
          边缘端 YOLO26n 实时检测作业人员与工程车辆，支持<b>手动划定多个危险作业区</b>，
          闯入即时标红告警并自动截屏存证；云端大模型深度研判，一键生成《施工安全巡检报告》。
        </p>
        <div class="cta">
          <el-button type="primary" size="large" round @click="focusAuth">立即体验</el-button>
          <el-button size="large" round @click="scrollFeatures">了解功能</el-button>
        </div>
        <div class="stats">
          <div v-for="s in stats" :key="s.label" class="stat">
            <div class="stat-num">{{ s.num }}</div>
            <div class="stat-label">{{ s.label }}</div>
          </div>
        </div>
      </div>

      <!-- 认证卡片 -->
      <div class="auth-card" ref="authCard">
        <el-tabs v-model="tab" stretch class="auth-tabs">
          <el-tab-pane label="登录" name="login">
            <el-form :model="loginForm" :rules="rules" ref="loginRef" size="large" @keyup.enter="doLogin">
              <el-form-item prop="username">
                <el-input v-model="loginForm.username" placeholder="用户名" :prefix-icon="User" />
              </el-form-item>
              <el-form-item prop="password">
                <el-input v-model="loginForm.password" type="password" placeholder="密码" show-password :prefix-icon="Lock" />
              </el-form-item>
              <el-button class="submit" type="primary" size="large" round :loading="loading" @click="doLogin">
                登 录
              </el-button>
            </el-form>
          </el-tab-pane>
          <el-tab-pane label="注册" name="register">
            <el-form :model="regForm" :rules="rules" ref="regRef" size="large" @keyup.enter="doRegister">
              <el-form-item prop="username">
                <el-input v-model="regForm.username" placeholder="用户名（登录用）" :prefix-icon="User" />
              </el-form-item>
              <el-form-item prop="nickname">
                <el-input v-model="regForm.nickname" placeholder="昵称（可选）" :prefix-icon="Postcard" />
              </el-form-item>
              <el-form-item prop="password">
                <el-input v-model="regForm.password" type="password" placeholder="密码（至少 6 位）" show-password :prefix-icon="Lock" />
              </el-form-item>
              <el-button class="submit" type="primary" size="large" round :loading="loading" @click="doRegister">
                注册并进入
              </el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>
        <div class="auth-tip">数据仅存于本机 SQLite，放心试用</div>
      </div>
    </section>

    <!-- 功能特性 -->
    <section class="features" ref="featuresEl">
      <div v-for="f in features" :key="f.title" class="feature-card">
        <div class="f-icon" :style="{ background: f.color }">
          <el-icon :size="22"><component :is="f.icon" /></el-icon>
        </div>
        <h3>{{ f.title }}</h3>
        <p>{{ f.desc }}</p>
      </div>
    </section>

    <footer class="foot">智慧工地安全巡检平台 · 端云协同 AI 推理应用</footer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Postcard, Cpu, WarningFilled, Document, Picture, Monitor, Setting } from '@element-plus/icons-vue'
import { useAuth } from '../stores/auth'
import { login as apiLogin, register as apiRegister } from '../api'

const router = useRouter()
const { state: authState, setAuth, refresh } = useAuth()

const tab = ref('login')
const loading = ref(false)
const authCard = ref(null)
const featuresEl = ref(null)
const loginRef = ref(null)
const regRef = ref(null)

const loginForm = reactive({ username: '', password: '' })
const regForm = reactive({ username: '', password: '', nickname: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' }
  ]
}

const stats = [
  { num: 'YOLO26n', label: '边缘实时检测' },
  { num: '多区域', label: '危险区手动划定' },
  { num: '5s 防抖', label: '闯入自动截屏' },
  { num: '7×24', label: '监控切页面不中断' }
]

const features = [
  { icon: Cpu, color: 'linear-gradient(135deg,#2563eb,#3b82f6)', title: '端云协同推理', desc: '边缘端 YOLO26n（CPU）实时检测，云端大模型深度理解，算力在端云间合理分工。' },
  { icon: WarningFilled, color: 'linear-gradient(135deg,#ea580c,#f59e0b)', title: '多危险区预警', desc: '手动划定多个危险作业区，人员车辆闯入即刻标红，5 秒防抖自动截屏存证。' },
  { icon: Document, color: 'linear-gradient(135deg,#059669,#10b981)', title: 'AI 巡检报告', desc: '一键生成《施工安全巡检报告》：图中人物及数量 / 安全危险情况 / 总结。' },
  { icon: Picture, color: 'linear-gradient(135deg,#7c3aed,#a78bfa)', title: '相册管理', desc: '截图自动入库，文件夹分类整理，多选批量移动/删除，相册图片可随时再次巡检。' },
  { icon: Monitor, color: 'linear-gradient(135deg,#0891b2,#22d3ee)', title: '持续监控', desc: '浏览器直连本机摄像头，开启后切换页面监控不中断，仅手动停止，云端部署也能用。' },
  { icon: Setting, color: 'linear-gradient(135deg,#475569,#94a3b8)', title: '个人中心', desc: '头像、昵称、个性签名、主题色个性化设置，数据全部存于本机数据库。' }
]

function focusAuth() {
  authCard.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
function scrollFeatures() {
  featuresEl.value?.scrollIntoView({ behavior: 'smooth' })
}

// 已登录用户刷新页面：校验 token 有效则直接进入应用
onMounted(async () => {
  if (authState.token) {
    const user = await refresh()
    if (user) router.push('/app/inspect')
  }
})

async function doLogin() {
  loading.value = true
  try {
    await loginRef.value?.validate()
    const { data } = await apiLogin(loginForm.username, loginForm.password)
    setAuth(data.token, data.user)
    ElMessage.success(`欢迎回来，${data.user.nickname || data.user.username}`)
    await router.push('/app/inspect')
  } catch (e) {
    if (e?.response?.status === 401) ElMessage.error('用户名或密码错误')
    else if (e?.response) ElMessage.error(e.response.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function doRegister() {
  loading.value = true
  try {
    await regRef.value?.validate()
    const { data } = await apiRegister(regForm.username, regForm.password, regForm.nickname)
    setAuth(data.token, data.user)
    ElMessage.success('注册成功，已自动登录')
    await router.push('/app/inspect')
  } catch (e) {
    if (e?.response) ElMessage.error(e.response.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.landing {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: #0b1220;
  color: #e2e8f0;
}

/* ---- 动态背景 ---- */
.bg {
  position: fixed;
  inset: 0;
  z-index: 0;
}
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.5;
  animation: float 14s ease-in-out infinite;
}
.orb-1 {
  width: 480px;
  height: 480px;
  background: #2563eb;
  top: -120px;
  left: -100px;
}
.orb-2 {
  width: 420px;
  height: 420px;
  background: #7c3aed;
  bottom: -140px;
  right: -80px;
  animation-delay: -7s;
}
.grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.07) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse at 50% 30%, #000 30%, transparent 75%);
}
@keyframes float {
  50% { transform: translate(40px, 30px) scale(1.08); }
}

/* ---- 布局 ---- */
.top, .hero, .features, .foot {
  position: relative;
  z-index: 1;
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 48px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 16px;
}
.logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  font-weight: 700;
}

.hero {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 48px;
  align-items: center;
  padding: 56px 48px 72px;
  max-width: 1200px;
  margin: 0 auto;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border: 1px solid rgba(96, 165, 250, 0.35);
  border-radius: 999px;
  font-size: 13px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.12);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 8px #22c55e;
}
.hero h1 {
  margin: 20px 0 16px;
  font-size: 46px;
  line-height: 1.2;
  font-weight: 800;
  color: #f8fafc;
}
.gradient-text {
  background: linear-gradient(90deg, #60a5fa, #a78bfa, #f472b6);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.sub {
  font-size: 16px;
  line-height: 1.8;
  color: #94a3b8;
  max-width: 540px;
}
.cta {
  display: flex;
  gap: 14px;
  margin: 28px 0 40px;
}
.stats {
  display: flex;
  gap: 36px;
}
.stat-num {
  font-size: 20px;
  font-weight: 700;
  color: #f1f5f9;
}
.stat-label {
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
}

/* ---- 认证卡片 ---- */
.auth-card {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  padding: 24px 24px 12px;
  backdrop-filter: blur(18px);
  box-shadow: 0 24px 60px rgba(2, 6, 23, 0.5);
}
.auth-tabs :deep(.el-tabs__item) {
  color: #94a3b8;
  font-size: 16px;
}
.auth-tabs :deep(.el-tabs__item.is-active) {
  color: #fff;
}
.submit {
  width: 100%;
  margin-top: 4px;
}
.auth-tip {
  text-align: center;
  font-size: 12px;
  color: #475569;
  padding: 8px 0 4px;
}

/* ---- 功能卡 ---- */
.features {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 48px 56px;
}
.feature-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 22px;
  transition: transform 0.25s, border-color 0.25s;
}
.feature-card:hover {
  transform: translateY(-4px);
  border-color: rgba(96, 165, 250, 0.4);
}
.f-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 11px;
  color: #fff;
  margin-bottom: 14px;
}
.feature-card h3 {
  margin: 0 0 8px;
  font-size: 16px;
  color: #f1f5f9;
}
.feature-card p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #94a3b8;
}

.foot {
  text-align: center;
  padding: 20px;
  font-size: 12px;
  color: #475569;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

@media (max-width: 960px) {
  .hero { grid-template-columns: 1fr; padding: 32px 24px 48px; }
  .hero h1 { font-size: 34px; }
  .features { grid-template-columns: repeat(2, 1fr); padding: 0 24px 40px; }
  .top { padding: 16px 24px; }
}
@media (max-width: 640px) {
  .features { grid-template-columns: 1fr; }
  .stats { gap: 20px; }
}
</style>
