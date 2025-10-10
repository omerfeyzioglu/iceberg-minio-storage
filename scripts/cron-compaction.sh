#!/bin/bash
# Cron Job Script - Her gece 23:00'da compaction çalıştırır
# Kurulum: crontab -e
# Ekle: 0 23 * * * /path/to/iceberg-minio-tiering/scripts/cron-compaction.sh >> /var/log/iceberg-compaction.log 2>&1

set -e

# Script dizini
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Log başlangıcı
echo "========================================"
echo "🌙 Nightly Compaction Job"
echo "⏰ $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

# Docker container'ın çalıştığını kontrol et
if ! docker ps | grep -q spark-master; then
    echo "❌ HATA: spark-master container çalışmıyor!"
    echo "Container'ları başlatın: cd $PROJECT_DIR && docker-compose up -d"
    exit 1
fi

# Compaction job'ı çalıştır
echo "🔄 Compaction başlatılıyor..."
docker exec spark-master python /scripts/compaction_job.py

# Sonuç
if [ $? -eq 0 ]; then
    echo "✅ Compaction job başarıyla tamamlandı!"
    echo "⏰ Bitiş: $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo "❌ Compaction job başarısız!"
    echo "⏰ Bitiş: $(date '+%Y-%m-%d %H:%M:%S')"
    exit 1
fi

echo "========================================"
echo ""

