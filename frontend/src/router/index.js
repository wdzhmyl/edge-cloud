import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'

const { state: authState } = useAuth()

const routes = [
  {
    path: '/',
    name: 'landing',
    component: () => import('../views/LandingView.vue'),
    meta: { public: true, title: '智慧工地安全巡检平台' }
  },
  {
    path: '/app',
    component: () => import('../views/AppShell.vue'),
    redirect: '/app/inspect',
    children: [
      {
        path: 'inspect',
        name: 'inspect',
        component: () => import('../views/InspectView.vue'),
        meta: { title: '图片巡检' }
      },
      {
        path: 'monitor',
        name: 'monitor',
        component: () => import('../views/MonitorView.vue'),
        meta: { title: '实时监控' }
      },
      {
        path: 'album',
        name: 'album',
        component: () => import('../views/AlbumView.vue'),
        meta: { title: '相册' }
      },
      {
        path: 'help',
        name: 'help',
        component: () => import('../views/HelpView.vue'),
        meta: { title: '使用手册' }
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('../views/ProfileView.vue'),
        meta: { title: '个人中心' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 未登录访问应用页 → 回前导页
router.beforeEach((to) => {
  if (!to.meta.public && !authState.token) {
    return { path: '/' }
  }
  if (to.meta.title) document.title = `${to.meta.title} · 智慧工地安全巡检平台`
})

export default router
