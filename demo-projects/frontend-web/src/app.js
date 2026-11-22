export function greet(name) {
  if (!name || !name.trim()) {
    return 'Hello, world';
  }
  return `Hello, ${name}`;
}

// 仅在浏览器环境操作 DOM，Node 单元测试导入本模块时不执行。
if (typeof document !== 'undefined') {
  const target = document.querySelector('#app');
  if (target) {
    target.textContent = greet('GitLab');
  }
}
