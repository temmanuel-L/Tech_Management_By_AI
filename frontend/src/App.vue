<template>
  <div id="app-root">
    <header class="app-header">
      <div class="header-content">
        <h1 class="logo">
          <span class="logo-icon">📊</span>
          <span>AI 技术管理工具</span>
        </h1>
        <p class="subtitle">基于《An Elegant Puzzle》· 数据驱动的管理决策支持</p>
      </div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
</script>

<style>
/* ======= 全局设计系统 ======= */
:root {
  --bg-primary: #0f1117;
  --bg-secondary: #1a1d2e;
  --bg-card: #1e2235;
  --bg-card-hover: #252a42;
  --border-color: rgba(255, 255, 255, 0.06);
  --text-primary: #e8eaf6;
  --text-secondary: #9fa8c7;
  --text-muted: #6b7394;
  --accent-green: #4caf50;
  --accent-blue: #42a5f5;
  --accent-orange: #ffa726;
  --accent-red: #ef5350;
  --accent-purple: #ab47bc;
  --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  --gradient-health: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
  --gradient-danger: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  --shadow-card: 0 4px 24px rgba(0, 0, 0, 0.3);
  --shadow-glow: 0 0 20px rgba(102, 126, 234, 0.15);
  --radius: 16px;
  --radius-sm: 10px;
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: var(--font-family);
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

.app-header {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  padding: 20px 32px;
  backdrop-filter: blur(10px);
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
}

.logo {
  font-size: 1.5rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.logo-icon {
  font-size: 1.8rem;
  -webkit-text-fill-color: initial;
}

.subtitle {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-top: 4px;
}

.app-main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px 32px;
}
</style>
