#!/bin/bash

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Apache Iceberg + MinIO Multi-Tier Storage                 ║"
echo "║   Hızlı Başlangıç Script                                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Renk kodları
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Hata kontrolü
set -e

step=1
total_steps=7

print_step() {
    echo -e "\n${BLUE}[${step}/${total_steps}]${NC} $1"
    ((step++))
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 1. Gereksinim kontrolü
print_step "Gereksinimler kontrol ediliyor..."

if ! command -v docker &> /dev/null; then
    print_error "Docker bulunamadı! Lütfen Docker Desktop kurun."
    exit 1
fi
print_success "Docker mevcut"

if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose bulunamadı!"
    exit 1
fi
print_success "docker-compose mevcut"

# 2. JAR dosyalarını kontrol et/indir
print_step "JAR dosyaları kontrol ediliyor..."

mkdir -p jars

JARS=(
    "iceberg-spark-runtime-3.5_2.12-1.5.2.jar"
    "aws-java-sdk-bundle-1.12.262.jar"
    "hadoop-aws-3.3.4.jar"
)

for jar in "${JARS[@]}"; do
    if [ -f "jars/$jar" ]; then
        print_success "$jar mevcut"
    else
        print_warning "$jar bulunamadı, indiriliyor..."
        case "$jar" in
            "iceberg-spark-runtime-3.5_2.12-1.5.2.jar")
                curl -L "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.2/iceberg-spark-runtime-3.5_2.12-1.5.2.jar" \
                    -o "jars/$jar"
                ;;
            "aws-java-sdk-bundle-1.12.262.jar")
                curl -L "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar" \
                    -o "jars/$jar"
                ;;
            "hadoop-aws-3.3.4.jar")
                curl -L "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar" \
                    -o "jars/$jar"
                ;;
        esac
        print_success "$jar indirildi"
    fi
done

# 3. Docker container'ları başlat
print_step "Docker container'ları başlatılıyor..."

docker-compose down -v 2>/dev/null || true
docker-compose up -d

print_success "Container'lar başlatıldı"

# 4. Container'ların hazır olmasını bekle
print_step "Container'lar hazır olması bekleniyor..."

echo -n "MinIO HOT bekleniyor"
for i in {1..30}; do
    if docker exec minio-hot mc ready local 2>/dev/null; then
        echo ""
        print_success "MinIO HOT hazır"
        break
    fi
    echo -n "."
    sleep 1
done

echo -n "MinIO COLD bekleniyor"
for i in {1..30}; do
    if docker exec minio-cold mc ready local 2>/dev/null; then
        echo ""
        print_success "MinIO COLD hazır"
        break
    fi
    echo -n "."
    sleep 1
done

sleep 5  # Spark için extra bekleme

# 5. MinIO Setup
print_step "MinIO yapılandırılıyor..."

docker exec minio-mc bash /scripts/setup-minio.sh
print_success "MinIO yapılandırması tamamlandı"

# 6. Iceberg tablo ve veri oluştur
print_step "Iceberg tablosu ve veri oluşturuluyor..."

docker exec spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar \
    /scripts/ingest_data.py

print_success "Veri yükleme tamamlandı"

# 7. Özet
print_step "Kurulum tamamlandı! 🎉"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    SİSTEM HAZIR!                             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Web UI'lar:"
echo "   • Spark Master:  http://localhost:8081"
echo "   • MinIO HOT:     http://localhost:9001  (minioadmin/minioadmin)"
echo "   • MinIO COLD:    http://localhost:9101  (minioadmin/minioadmin)"
echo ""
echo "🔧 Hızlı Komutlar:"
echo "   • Veri sorgula:"
echo "     docker exec -it spark-master /opt/spark/bin/spark-sql \\"
echo "       --master spark://spark-master:7077 \\"
echo "       --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar \\"
echo "       --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog \\"
echo "       --conf spark.sql.catalog.iceberg.type=hadoop \\"
echo "       --conf spark.sql.catalog.iceberg.warehouse=s3a://iceberg-warehouse/ \\"
echo "       --conf spark.hadoop.fs.s3a.endpoint=http://minio-hot:9000 \\"
echo "       --conf spark.hadoop.fs.s3a.access.key=minioadmin \\"
echo "       --conf spark.hadoop.fs.s3a.secret.key=minioadmin \\"
echo "       --conf spark.hadoop.fs.s3a.path.style.access=true \\"
echo "       --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false \\"
echo "       --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \\"
echo "       --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \\"
echo "       -e \"SELECT * FROM iceberg.db.transactions LIMIT 10\""
echo ""
echo "   • Tiering (HOT → COLD):"
echo "     docker exec minio-mc python3 /scripts/tiering_job.py --age-days 1 --no-dry-run"
echo ""
echo "   • MinIO bucket'ları:"
echo "     docker exec minio-mc mc ls hot/"
echo "     docker exec minio-mc mc ls cold/"
echo ""
echo "📚 Detaylı bilgi: KURULUM.md"
echo ""

