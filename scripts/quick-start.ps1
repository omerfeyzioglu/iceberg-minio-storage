# Apache Iceberg + MinIO Multi-Tier Storage - Hızlı Başlangıç (Windows)

Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Apache Iceberg + MinIO Multi-Tier Storage                 ║" -ForegroundColor Cyan
Write-Host "║   Hızlı Başlangıç Script (Windows)                           ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$step = 1
$totalSteps = 7

function Print-Step {
    param($message)
    Write-Host "`n[$script:step/$totalSteps] $message" -ForegroundColor Blue
    $script:step++
}

function Print-Success {
    param($message)
    Write-Host "✓ $message" -ForegroundColor Green
}

function Print-Error {
    param($message)
    Write-Host "✗ $message" -ForegroundColor Red
}

function Print-Warning {
    param($message)
    Write-Host "⚠ $message" -ForegroundColor Yellow
}

# 1. Gereksinim kontrolü
Print-Step "Gereksinimler kontrol ediliyor..."

try {
    docker --version | Out-Null
    Print-Success "Docker mevcut"
} catch {
    Print-Error "Docker bulunamadı! Lütfen Docker Desktop kurun."
    exit 1
}

try {
    docker-compose --version | Out-Null
    Print-Success "docker-compose mevcut"
} catch {
    Print-Error "docker-compose bulunamadı!"
    exit 1
}

# 2. JAR dosyalarını kontrol et/indir
Print-Step "JAR dosyaları kontrol ediliyor..."

New-Item -ItemType Directory -Force -Path "jars" | Out-Null

$jars = @{
    "iceberg-spark-runtime-3.5_2.12-1.5.2.jar" = "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.2/iceberg-spark-runtime-3.5_2.12-1.5.2.jar"
    "aws-java-sdk-bundle-1.12.262.jar" = "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar"
    "hadoop-aws-3.3.4.jar" = "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar"
}

foreach ($jar in $jars.Keys) {
    if (Test-Path "jars\$jar") {
        Print-Success "$jar mevcut"
    } else {
        Print-Warning "$jar bulunamadı, indiriliyor..."
        Invoke-WebRequest -Uri $jars[$jar] -OutFile "jars\$jar"
        Print-Success "$jar indirildi"
    }
}

# 3. Docker container'ları başlat
Print-Step "Docker container'ları başlatılıyor..."

docker-compose down -v 2>$null
docker-compose up -d

Print-Success "Container'lar başlatıldı"

# 4. Container'ların hazır olmasını bekle
Print-Step "Container'lar hazır olması bekleniyor..."

Write-Host "MinIO HOT bekleniyor" -NoNewline
for ($i = 1; $i -le 30; $i++) {
    try {
        docker exec minio-hot mc ready local 2>$null | Out-Null
        Write-Host ""
        Print-Success "MinIO HOT hazır"
        break
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
}

Write-Host "MinIO COLD bekleniyor" -NoNewline
for ($i = 1; $i -le 30; $i++) {
    try {
        docker exec minio-cold mc ready local 2>$null | Out-Null
        Write-Host ""
        Print-Success "MinIO COLD hazır"
        break
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
}

Start-Sleep -Seconds 5  # Spark için extra bekleme

# 5. MinIO Setup
Print-Step "MinIO yapılandırılıyor..."

docker exec minio-mc bash /scripts/setup-minio.sh
Print-Success "MinIO yapılandırması tamamlandı"

# 6. Iceberg tablo ve veri oluştur
Print-Step "Iceberg tablosu ve veri oluşturuluyor..."

docker exec spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar `
    /scripts/ingest_data.py

Print-Success "Veri yükleme tamamlandı"

# 7. Özet
Print-Step "Kurulum tamamlandı! 🎉"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                    SİSTEM HAZIR!                             ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "📊 Web UI'lar:" -ForegroundColor Yellow
Write-Host "   • Spark Master:  http://localhost:8081"
Write-Host "   • MinIO HOT:     http://localhost:9001  (minioadmin/minioadmin)"
Write-Host "   • MinIO COLD:    http://localhost:9101  (minioadmin/minioadmin)"
Write-Host ""
Write-Host "🔧 Hızlı Komutlar:" -ForegroundColor Yellow
Write-Host ""
Write-Host "Veri Sorgula:" -ForegroundColor Green
Write-Host @"
docker exec -it spark-master /opt/spark/bin/spark-sql ``
  --master spark://spark-master:7077 ``
  --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar ``
  --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog ``
  --conf spark.sql.catalog.iceberg.type=hadoop ``
  --conf spark.sql.catalog.iceberg.warehouse=s3a://iceberg-warehouse/ ``
  --conf spark.hadoop.fs.s3a.endpoint=http://minio-hot:9000 ``
  --conf spark.hadoop.fs.s3a.access.key=minioadmin ``
  --conf spark.hadoop.fs.s3a.secret.key=minioadmin ``
  --conf spark.hadoop.fs.s3a.path.style.access=true ``
  --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false ``
  --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem ``
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions ``
  -e "SELECT * FROM iceberg.db.transactions LIMIT 10"
"@
Write-Host ""
Write-Host "Tiering (HOT → COLD):" -ForegroundColor Green
Write-Host "docker exec minio-mc python3 /scripts/tiering_job.py --age-days 1 --no-dry-run"
Write-Host ""
Write-Host "MinIO Kontrol:" -ForegroundColor Green
Write-Host "docker exec minio-mc mc ls hot/"
Write-Host "docker exec minio-mc mc ls cold/"
Write-Host ""
Write-Host "📚 Detaylı bilgi: KURULUM.md" -ForegroundColor Cyan
Write-Host ""

