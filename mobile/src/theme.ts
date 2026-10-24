// Dark cyberpunk theme matching the PC dashboard (static/index.html).

export const colors = {
  bg: '#070a0f',
  panel: '#0d131d',
  panelLight: '#131b29',
  inputBg: '#080c14',
  border: '#1a2536',
  borderLight: '#2e4463',
  text: '#d1d9e6',
  dim: '#677b96',
  cyan: '#00f0ff',
  green: '#00ff88',
  yellow: '#ffb800',
  red: '#ff3366',
  orange: '#ff8800',
  purple: '#b55fe6',
};

export function statusColor(status: string): string {
  switch (status) {
    case 'running': return colors.yellow;
    case 'completed': return colors.green;
    case 'failed': return colors.red;
    case 'cancelled': return colors.orange;
    case 'idle': return colors.cyan;
    default: return colors.dim; // pending
  }
}
