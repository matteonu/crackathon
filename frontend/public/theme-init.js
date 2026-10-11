// Restore before the app stylesheet paints, including when storage is disabled.
try {
  const theme = localStorage.getItem('studyhub.theme');
  if (['green', 'yellow', 'blue', 'red', 'dark', 'contrast', 'colorblind'].includes(theme)) {
    document.documentElement.dataset.theme = theme;
  }
} catch { /* The default Green theme remains available. */ }
