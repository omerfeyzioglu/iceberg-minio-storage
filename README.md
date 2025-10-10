# 🗄️ Apache Iceberg + MinIO Multi-Tier Storage

Apache Iceberg table format ile MinIO HOT/COLD tier mimarisi.

## 🎯 Özellikler

- ✅ Apache Iceberg Format v2
- ✅ MinIO HOT tier (Primary Storage)
- ✅ MinIO COLD tier (Archive Storage)
- ✅ Spark 3.5.0 (Master + Worker)
- ✅ Date-based partitioning
- ✅ ZSTD compression
- ✅ Manuel tiering script
- ✅ Time travel & snapshots

## 🚀 Hızlı Başlangıç

### 1. Gereksinimler
- Docker Desktop
- PowerShell / Bash
- 8GB+ RAM

### 2. Kurulum

Detaylı kurulum için: **[KURULUM.md](./KURULUM.md)**

```powershell
# 1. Repoyu klonla veya dosyaları indir
git clone <repo-url>
cd iceberg-minio-tiering

# 2. JAR'ları indir
bash scripts/download-jars.sh
# VEYA Windows:
# Invoke-WebRequest komutlarını KURULUM.md'den kopyala

# 3. Docker'ı başlat
docker-compose up -d

# 4. MinIO setup
docker exec minio-mc bash /scripts/setup-minio.sh

# 5. Veri yükle
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar \
  /scripts/ingest_data.py
```

## 📂 Proje Yapısı

```
iceberg-minio-tiering/
├── docker-compose.yml          # Container tanımları
├── KURULUM.md                  # Detaylı kurulum kılavuzu
├── README.md                   # Bu dosya
├── .gitignore                  # Git ignore kuralları
│
├── jars/                       # Spark JAR'ları
│   ├── iceberg-spark-runtime-3.5_2.12-1.5.2.jar
│   ├── aws-java-sdk-bundle-1.12.262.jar
│   └── hadoop-aws-3.3.4.jar
│
├── scripts/                    # Python & Bash scriptler
│   ├── download-jars.sh        # JAR indirme
│   ├── setup-minio.sh          # MinIO setup
│   ├── ingest_data.py          # Veri ingestion
│   ├── compaction_job.py       # Compaction (opsiyonel)
│   └── tiering_job.py          # HOT → COLD tiering
│
├── spark-config/               # Spark konfigürasyonları
│   └── spark-defaults.conf     # Spark default ayarları
│
└── data/                       # Veri klasörü (gitignore)
    ├── minio-hot/              # HOT tier storage
    └── minio-cold/             # COLD tier storage
```

## 🔧 Kullanım

### Veri Sorgulama
```powershell
docker exec -it spark-master /opt/spark/bin/spark-sql \
  --master spark://spark-master:7077 \
  --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar \
  --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.iceberg.type=hadoop \
  --conf spark.sql.catalog.iceberg.warehouse=s3a://iceberg-warehouse/ \
  --conf spark.hadoop.fs.s3a.endpoint=http://minio-hot:9000 \
  --conf spark.hadoop.fs.s3a.access.key=minioadmin \
  --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
  --conf spark.hadoop.fs.s3a.path.style.access=true \
  --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false \
  --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  -e "SELECT * FROM iceberg.db.transactions LIMIT 10"
```

### Manuel Tiering (HOT → COLD)
```powershell
# Dry run (test)
docker exec minio-mc python3 /scripts/tiering_job.py --age-days 1

# Gerçek transfer
docker exec minio-mc python3 /scripts/tiering_job.py --age-days 1 --no-dry-run
```

### MinIO Kontrol
```powershell
# HOT bucket'lar
docker exec minio-mc mc ls hot/

# COLD bucket
docker exec minio-mc mc ls --recursive cold/iceberg-cold-tier/

# Tier bilgisi
docker exec minio-mc mc admin tier ls hot
```

## 🌐 Web UI'lar

- **Spark Master UI:** http://localhost:8081
- **MinIO HOT UI:** http://localhost:9001 (minioadmin/minioadmin)
- **MinIO COLD UI:** http://localhost:9101 (minioadmin/minioadmin)

## 📊 Mimari

```
┌─────────────────────────────────────────────┐
│           Apache Iceberg Table              │
│         (Format v2, Partitioned)            │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│          Spark 3.5.0 Cluster                │
│        (Master + Worker + PySpark)          │
└─────────────────────────────────────────────┘
                    ↓
┌──────────────────────┬──────────────────────┐
│    MinIO HOT         │    MinIO COLD        │
│  (9000/9001)         │  (9100/9101)         │
│                      │                      │
│  • Metadata (always) │  • Old Data (1+ day) │
│  • Fresh Data        │  • Manual Tiering    │
└──────────────────────┴──────────────────────┘
```

## 🔑 Önemli Bilgiler

### MinIO ILM (Lifecycle Management)
- ❌ **Community Edition'da çalışmıyor**
- ✅ **Manuel script kullan:** `tiering_job.py`
- ⚠️ Scanner pasif/yavaş (2 hafta test edildi)

### Iceberg Metadata
- ✅ **Her zaman HOT'da kalır** (metadata/)
- ✅ **Data dosyaları COLD'a taşınır** (data/)
- ✅ **Transparent okuma** (Iceberg otomatik bulur)

### Compression
- **Ingestion:** ZSTD Level 3 (hızlı)
- **Compaction:** ZSTD Level 9 (maksimum sıkıştırma)

## 🔍 Troubleshooting

### Container başlamıyor
```powershell
docker-compose down -v
docker-compose up -d
docker-compose ps
```

### JAR hataları
```powershell
ls -la jars/
# Her JAR dosyası ~50-150MB olmalı
```

### MinIO bağlantı hatası
```powershell
docker exec minio-mc mc alias ls
docker exec minio-mc mc ping hot/iceberg-warehouse --count 3
```

### Iceberg tablo bulunamıyor
```powershell
docker exec -it spark-master /opt/spark/bin/spark-sql \
  --master spark://spark-master:7077 \
  -e "SHOW DATABASES"
```

## 📚 Kaynaklar

- [Apache Iceberg](https://iceberg.apache.org/)
- [MinIO Docs](https://min.io/docs/)
- [Spark SQL Guide](https://spark.apache.org/docs/latest/sql-programming-guide.html)

## 📝 Lisans

MIT License

---

**Not:** Bu proje test/development amaçlıdır. Production için ek güvenlik ve optimizasyon gerekir.
