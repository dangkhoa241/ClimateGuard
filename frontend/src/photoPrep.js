// Damage photos are re-drawn on a canvas before upload: upright (the phone's rotation flag is applied),
// at most 1280 px on the long side, saved as a fresh JPEG. A canvas JPEG carries no EXIF, so location (GPS),
// time and camera data never leave the phone; the server strips metadata again (backend photos.py).
// 1280 px keeps each photo ~1,400 model tokens and ~200-400 KB on mobile data.
const MAX_SIDE = 1280
const MAX_BYTES = 1_400_000

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => resolve({ source: img, release: () => URL.revokeObjectURL(url) })
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('photo_unreadable'))
    }
    img.src = url
  })
}

async function decode(file) {
  if (window.createImageBitmap) {
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' })
      return { source: bmp, release: () => bmp.close() }
    } catch {
      // older Safari or an unsupported option: fall back to <img>, which also applies the rotation flag
    }
  }
  return loadImage(file)
}

const toJpeg = (canvas, quality) =>
  new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))

export async function preparePhoto(file) {
  const { source, release } = await decode(file)
  try {
    const w = source.width || source.naturalWidth
    const h = source.height || source.naturalHeight
    if (!w || !h) throw new Error('photo_unreadable')
    const scale = Math.min(1, MAX_SIDE / Math.max(w, h))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(w * scale)
    canvas.height = Math.round(h * scale)
    canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height)
    let blob = await toJpeg(canvas, 0.85)
    if (blob && blob.size > MAX_BYTES) blob = await toJpeg(canvas, 0.7)
    if (!blob) throw new Error('photo_unreadable')
    return { blob, url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height }
  } finally {
    release()
  }
}
