<template>
  <div class="help-view">
    <el-card>
      <template #header><span>使用说明</span></template>

      <h3>实时监控</h3>
      <ol>
        <li>点击「搜索摄像头」自动发现本机摄像头；</li>
        <li>
          手机摄像头：安装 IP 摄像头 App（如 IP Webcam / DroidCam），将地址（如
          <code>http://手机IP:8080/video</code> 或 <code>rtsp://...</code>）粘贴到输入框并点击「添加」；
        </li>
        <li>在下拉框选择摄像头，点击「开启监控」开始逐帧检测；</li>
        <li>监控开启后<strong>切换到其他页面不会中断</strong>，只有手动点「停止监控」才关闭；</li>
        <li>检测到危险作业区闯入时每 5 秒最多自动截屏一次，也可随时点击「主动截屏」（截图仅保留最新 4 张）；</li>
        <li>「划定危险区域」：在画面上按住拖拽框选，可划多个，旧区域保留，右侧列表可单独删除。</li>
      </ol>

      <h3>危险作业区规则</h3>
      <p>
        推荐<strong>手动划定</strong>：监控页点「划定危险区域」在画面上拖拽框选即可，支持多个区域、按用户保存。
        默认区域也可在 <code>config/settings.py</code> 的 <code>DANGER_ZONE</code> 中调整，或设
        <code>ENABLE_DANGER_ZONE=False</code> 关闭。
      </p>

      <h3>相册</h3>
      <p>
        监控截图自动收入「巡检截图」文件夹；支持新建文件夹分类、「多选」后批量移动/删除；
        每张图片可点 🔍 直接巡检（检测 + 云端报告）。
      </p>

      <h3>云端大模型配置</h3>
      <p>
        将 <code>.env.example</code> 复制为 <code>.env</code>，填入
        <code>LLM_BASE_URL</code>、<code>LLM_API_KEY</code>、<code>LLM_MODEL</code>
        后重启后端即可启用云端智能研判，无需改动代码。未配置时自动使用本地兜底报告。
      </p>

      <h3>识别能力</h3>
      <p>
        边缘端可识别：作业人员、非机动车、摩托车、通勤车辆、通勤班车、工程运输车、现场信号灯、消防栓、警示标识等，
        并对危险作业区闯入做实时规则化预警。
      </p>

      <h3>架构说明（v2.0 前后端分离）</h3>
      <ul>
        <li>后端：<code>interfaces/api.py</code>（FastAPI，端口 8000），接口前缀 <code>/api</code>，文档见 <code>/docs</code>；</li>
        <li>前端：<code>frontend/</code>（Vue3 + Vite，端口 5173），开发时经 Vite 代理访问后端；</li>
        <li>核心逻辑：<code>pipeline/collab.py</code> 与 <code>core/</code> 未被改动，旧版 Gradio 网页（<code>interfaces/web.py</code>）仍可独立运行。</li>
      </ul>
    </el-card>
  </div>
</template>

<script setup>
</script>

<style scoped>
.help-view {
  line-height: 1.8;
}
h3 {
  color: #1f2937;
  margin: 16px 0 8px;
}
code {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}
</style>
