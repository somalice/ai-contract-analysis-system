/**
 * 格式化工具函数
 */

/**
 * 格式化文件大小(字节 → KB/MB/GB)
 * @param {number} bytes 字节数
 * @returns {string} 格式化后的字符串
 */
export function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const size = (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 2)
  return `${size} ${units[i]}`
}

/**
 * 格式化时间(已格式化的字符串原样返回;Date 对象转字符串)
 * 后端返回的时间格式为 'YYYY-MM-DD HH:MM:SS',直接展示
 * @param {string|Date} time 时间
 * @returns {string}
 */
export function formatTime(time) {
  if (!time) return '-'
  if (typeof time === 'string') return time
  if (time instanceof Date) {
    const pad = (n) => String(n).padStart(2, '0')
    return `${time.getFullYear()}-${pad(time.getMonth() + 1)}-${pad(time.getDate())} ` +
           `${pad(time.getHours())}:${pad(time.getMinutes())}:${pad(time.getSeconds())}`
  }
  return String(time)
}

/**
 * 截断过长的字符串
 * @param {string} str 原字符串
 * @param {number} maxLen 最大长度
 * @returns {string}
 */
export function truncate(str, maxLen = 50) {
  if (!str) return ''
  return str.length > maxLen ? str.substring(0, maxLen) + '...' : str
}
