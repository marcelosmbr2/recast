from recast.core.models import Preset

BUILTIN_PRESETS: list[Preset] = [
    Preset("p1", "Fotos do iPhone para JPG", ["heic", "heif"], "JPG", "image", 85,
           "Qualidade 85 · Remove localização", {"strip": True}, builtin=True),
    Preset("p2", "Imagens para web", ["png", "jpg", "jpeg", "tiff", "bmp"], "WEBP", "image", 80,
           "Qualidade 80 · Até 2560 px de largura", {"resize": "2560 px"}, builtin=True),
    Preset("p3", "Master de podcast", ["wav", "aiff", "flac", "m4a"], "MP3", "audio", 95,
           "320 kbps · Estéreo", {"bitrate": "320 kbps", "channels": "Estéreo"}, builtin=True),
    Preset("p4", "Vídeo para compartilhar", ["mov", "mkv", "avi", "webm", "m4v"], "MP4", "video", 80,
           "H.264 · 1080p · Equilibrado", {"codec": "H.264", "res": "1080p"}, builtin=True),
    Preset("p5", "Digitalizações para PDF", ["tiff", "tif"], "PDF", "document", 80,
           "Imagens comprimidas", {"compress": True}, builtin=True),
    Preset("p6", "Word para PDF", ["docx"], "PDF", "document", 80,
           "Documento portátil · Imagens comprimidas", {"compress": True}, builtin=True),
    Preset("p7", "PDF para Word", ["pdf"], "DOCX", "document", 80,
           "Somente o texto · Microsoft Word", builtin=True),
    Preset("p8", "OGG para MP3", ["ogg"], "MP3", "audio", 80,
           "192 kbps · Estéreo", {"bitrate": "192 kbps", "channels": "Estéreo"}, builtin=True),
]
