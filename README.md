# Apache Iceberg + MinIO + Spark Hot/Cold Tiering Sistemi
## Kapsamlı Kurulum ve Kullanım Dokümantasyonu

---

# İÇİNDEKİLER

1. [Sistem Mimarisi ve Bileşenler](#1-sistem-mimarisi-ve-bileşenler)
2. [Temel Kavramlar](#2-temel-kavramlar)
3. [Gereksinimler](#3-gereksinimler)
4. [Adım Adım Kurulum](#4-adım-adım-kurulum)
5. [Veri İşlemleri](#5-veri-i̇şlemleri)
6. [MinIO Tiering Yapılandırması](#6-minio-tiering-yapılandırması)
7. [Sorgulama ve Analiz](#7-sorgulama-ve-analiz)
8. [Bakım İşlemleri](#8-bakım-i̇şlemleri)
9. [Sorun Giderme](#9-sorun-giderme)
10. [Komut Referansı](#10-komut-referansi)

---

# 1. SISTEM MIMARISI VE BILEŞENLER

## 1.1. Genel Mimari

```
┌─────────────────────────────────────────────────────────────┐
│                    KULLANICI SORGUSU                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   APACHE SPARK CLUSTER                       │
│  ┌──────────────┐              ┌──────────────┐            │
│  │ Spark Master │◄────────────►│ Spark Worker │            │
│  │  Port: 8080  │              │              │            │
│  └──────────────┘              └──────────────┘            │
│         │                                                    │
│         │ (Iceberg Catalog API)                             │
│         ▼                                                    │
│  ┌──────────────────────────────────────────┐              │
│  │   Iceberg Table Format                   │              │
│  │   - Metadata Management                  │              │
│  │   - Schema Evolution                     │              │
│  │   - Time Travel                          │              │
│  │   - ACID Transactions                    │              │
│  └──────────────────────────────────────────┘              │
└────────────┬───────────────────────────────────────────────┘
             │ (S3A Protocol)
             ▼
┌─────────────────────────────────────────────────────────────┐
│                      MINIO HOT TIER                          │
│                      (Primary Storage)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Distributed Mode: /data1 /data2 /data3 /data4      │   │
│  │  Port: 9000 (API) | 9001 (Console)                  │   │
│  │  ILM Scanner: Active (1 minute interval)            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  Buckets:                                                    │
│  └── iceberg-warehouse/                                     │
│      ├── db/                                                │
│      │   └── transactions/                                  │
│      │       ├── data/                  ← Parquet Files    │
│      │       │   ├── date=2025-10-31/                      │
│      │       │   │   └── 00000-xxx.parquet                 │
│      │       │   └── date=2025-11-01/                      │
│      │       └── metadata/              ← Iceberg Metadata │
│      │           ├── v1.metadata.json                       │
│      │           ├── v2.metadata.json                       │
│      │           └── snap-xxx.avro                          │
│      └── metadata/                       ← Table Tracking   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ (ILM Transition - Transparent)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                      MINIO COLD TIER                         │
│                     (Archive Storage)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Distributed Mode: /data1 /data2 /data3 /data4      │   │
│  │  Port: 9100 (API) | 9101 (Console)                  │   │
│  │  Compression: Enabled (.parquet)                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  Buckets:                                                    │
│  └── iceberg-cold-tier/                                     │
│      └── db/                                                │
│          └── transactions/                                  │
│              └── data/                   ← Archived Files   │
│                  └── date=2025-10-31/                       │
│                      └── 00000-xxx.parquet                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      MINIO CLIENT (mc)                       │
│  - Alias Management (hot, cold)                             │
│  - Bucket Operations                                         │
│  - Tiering Configuration                                     │
│  - ILM Rule Management                                       │
└─────────────────────────────────────────────────────────────┘
```

## 1.2. Bileşenler Detayı

### A) MinIO HOT Tier (Primary Storage)
- **Amaç**: Ana veri deposu, sık erişilen veriler
- **Mod**: Distributed (4 disk: /data1, /data2, /data3, /data4)
- **Neden Distributed**: ILM scanner'ın çalışması için gerekli
- **Port**: 9000 (API), 9001 (Web Console)
- **Özellikler**:
  - ILM Scanner: 1 dakikada bir çalışır
  - S3-compatible API
  - Transparent tiering desteği

### B) MinIO COLD Tier (Archive Storage)
- **Amaç**: Eski/soğuk veri arşivleme
- **Mod**: Distributed (4 disk: /data1, /data2, /data3, /data4)
- **Port**: 9100 (API), 9101 (Web Console)
- **Özellikler**:
  - Parquet dosyaları için compression aktif
  - Düşük maliyetli depolama simülasyonu
  - Hot tier tarafından remote tier olarak kullanılır

### C) Apache Spark (3.5.0)
- **Master**: Cluster yönetimi, job scheduling
  - Port 8080: Web UI
  - Port 7077: Master endpoint
  - Port 4040: Application UI
- **Worker**: İş yükünü çalıştıran node
  - 4GB RAM, 2 core
- **Özellikler**:
  - Iceberg entegrasyonu
  - S3A FileSystem üzerinden MinIO erişimi
  - PySpark ile Python script desteği

### D) Apache Iceberg (1.5.2)
- **Amaç**: Modern data lake table format
- **Catalog Type**: Hadoop Catalog (file-based)
- **Warehouse**: s3a://iceberg-warehouse/
- **Özellikler**:
  - ACID transactions
  - Schema evolution
  - Time travel (snapshot bazlı)
  - Hidden partitioning
  - Metadata yönetimi

### E) MinIO Client (mc)
- **Amaç**: MinIO yönetim ve konfigürasyon
- **Kullanım Alanları**:
  - Bucket oluşturma/silme
  - Tiering yapılandırması
  - ILM rule yönetimi
  - Dosya listeleme/kopyalama

---

# 2. TEMEL KAVRAMLAR

## 2.1. Iceberg Kavramları

### Snapshot
- Her veri değişikliği (INSERT, UPDATE, DELETE) yeni bir snapshot oluşturur
- Snapshot ID ile geçmişe dönük sorgulama (time travel) yapılabilir
- Örnek: `SELECT * FROM tablo TIMESTAMP AS OF '2024-10-20 15:30:00'`

### Metadata
- **metadata.json**: Tablo şeması, partition bilgisi, snapshot listesi
- **manifest-list**: Snapshot'taki dosya gruplarının listesi
- **manifest**: Her partition'daki veri dosyalarının detayı
- **Avro format**: Hızlı okuma için binary format

### Partition
- Verilerin fiziksel organizasyonu
- Örnek: `PARTITIONED BY (date)` → Her gün için ayrı klasör
- Hidden partitioning: Kullanıcı WHERE date = 'X' yazarken arka planda partition'a yönlendirilir

### Compaction
- Küçük dosyaları birleştirerek sorgu performansını artırma
- **Binpack stratejisi**: Dosyaları hedef boyuta göre paketler
- Eski dosyalar snapshot'ta "deleted" olarak işaretlenir
- Orphan files: Hiçbir snapshot'ta referans edilmeyen dosyalar

## 2.2. MinIO Kavramları

### Bucket
- S3'teki "bucket" kavramı: Veri konteyner
- Örnek: `iceberg-warehouse`, `iceberg-cold-tier`

### Tier
- **HOT**: Sık erişilen, hızlı storage
- **COLD**: Eski/arşiv, yavaş ama ucuz storage
- MinIO'da remote tier olarak yapılandırılır

### ILM (Information Lifecycle Management)
- Otomatik veri yaşam döngüsü yönetimi
- **Transition**: Verinin HOT → COLD'a taşınması
- **Expiration**: Verinin silinmesi
- **Rule**: Hangi dosyaların ne zaman taşınacağını belirler
  - `--transition-days 0`: Hemen taşı
  - `--prefix "db/transactions/data/"`: Sadece bu prefix'teki dosyalar
  - `--tags "type=backfill"`: Sadece bu tag'li objeler

### Transparent Tiering
- COLD'a taşınan dosya, HOT'ta küçük bir stub (pointer) olarak kalır
- Kullanıcı hala aynı path'ten erişir: `s3a://iceberg-warehouse/...`
- MinIO arka planda COLD'dan veriyi getirir

### Object Tags
- Dosyalara key-value etiketler ekleme
- ILM rule'ları tag'lere göre filtreleme yapabilir
- Örnek: `mc tag set hot/bucket/path "type=backfill"`

## 2.3. Spark Kavramları

### SparkSession
- Spark cluster'a bağlantı noktası
- Konfigürasyonların yapıldığı yer

### Catalog
- Iceberg tabloları için catalog: `spark.sql.catalog.iceberg`
- Hadoop catalog: Metadata dosya sisteminde saklanır
- Warehouse path: `s3a://iceberg-warehouse/`

### S3A FileSystem
- Hadoop'un S3 protokolünü konuşan FileSystem implementasyonu
- `s3a://` URI scheme kullanır
- MinIO endpoint: `http://minio-hot:9000`
- Path-style access: `http://endpoint/bucket/key` (not virtual-hosted)

### DataFrame
- Spark'ta veri yapısı (SQL Table gibi)
- Transformations: map, filter, groupBy (lazy)
- Actions: show, count, write (eager, trigger execution)

---

# 3. GEREKSINIMLER

## 3.1. Yazılım Gereksinimleri

- **Docker**: 20.10+ 
- **Docker Compose**: 2.0+
- **Disk Alanı**: Minimum 20GB (test için), Production'da ihtiyaca göre
- **RAM**: Minimum 8GB (Spark worker için 4GB ayrılacak)
- **CPU**: 4+ core önerilir

## 3.2. Network Gereksinimleri

Kullanılan portlar:
- 9000: MinIO HOT API
- 9001: MinIO HOT Console
- 9100: MinIO COLD API
- 9101: MinIO COLD Console
- 8080: Spark Master UI
- 7077: Spark Master
- 4040: Spark Application UI

## 3.3. JAR Dosyaları

Aşağıdaki JAR dosyaları `jars/` klasöründe olmalı:

1. **iceberg-spark-runtime-3.5_2.12-1.5.2.jar**
   - Iceberg + Spark entegrasyonu
   - İndirme: https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.2/

2. **aws-java-sdk-bundle-1.12.262.jar**
   - S3 API client (MinIO için)
   - İndirme: https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/

3. **hadoop-aws-3.3.4.jar**
   - S3A FileSystem implementation
   - İndirme: https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/

### JAR'ların Görevi

#### 1. iceberg-spark-runtime-3.5_2.12-1.5.2.jar
**Amaç**: Apache Iceberg'i Spark'a entegre eder

**Sağladığı Özellikler**:
- Iceberg catalog: `CREATE TABLE ... USING iceberg`
- Partition evolution: Partition yapısını değiştirebilme
- Time travel: `SELECT ... TIMESTAMP AS OF '2024-10-20'`
- Snapshot management: `CALL iceberg.system.rollback_to_snapshot()`
- Schema evolution: Kolon ekleme/silme
- Hidden partitioning: Kullanıcı partition görmez, Iceberg otomatik yapar

**İsimlendirme**:
- `3.5`: Spark 3.5 ile uyumlu
- `2.12`: Scala 2.12 ile compile edilmiş
- `1.5.2`: Iceberg versiyonu

#### 2. aws-java-sdk-bundle-1.12.262.jar
**Amaç**: AWS S3 API'sini kullanmak için gerekli (MinIO S3 uyumlu)

**Sağladığı Özellikler**:
- S3 client: MinIO'ya S3 protokolü ile bağlan
- Authentication: Access key/secret key yönetimi
- Multipart upload: Büyük dosyaları parça parça yükle
- Metadata operations: Bucket/object listeleme, silme, kopyalama
- Presigned URLs: Geçici erişim linkleri

**Neden AWS SDK?**:
- MinIO, AWS S3 protokolünü kullanıyor
- Bu JAR, MinIO'yu "S3 gibi" görmemizi sağlıyor
- `aws-java-sdk-bundle` → Tüm AWS SDK modüllerini içerir (bundle = paket)
- Versiyon: 1.12.262 → AWS SDK v1 (v2 değil)

#### 3. hadoop-aws-3.3.4.jar
**Amaç**: Hadoop FileSystem'i S3 ile çalıştırır

**Sağladığı Özellikler**:
- S3AFileSystem: `s3a://` protokolünü destekler
- Credential providers: Access key'leri yönetir
- Performance optimization: Connection pooling, retry logic
- Integration: Spark'ın Hadoop ile entegrasyonu

**Neden Gerekli?**:
- Spark, dosya işlemleri için Hadoop FileSystem API kullanır
- MinIO S3 kullandığı için S3AFileSystem gerekli
- Bu JAR, `s3a://iceberg-warehouse/` gibi path'leri anlar

**S3A vs S3N**:
- `s3n://` → Eski, deprecated
- `s3a://` → Yeni, hızlı, multipart upload destekli

---

# 4. ADIM ADIM KURULUM

## ADIM 1: Proje Yapısını Oluşturma

### 1.1. Dizin Yapısı

```bash
iceberg-minio-tiering/
├── docker-compose.yml
├── jars/
│   ├── iceberg-spark-runtime-3.5_2.12-1.5.2.jar
│   ├── aws-java-sdk-bundle-1.12.262.jar
│   └── hadoop-aws-3.3.4.jar
├── spark-config/
│   └── spark-defaults.conf
├── scripts/
│   ├── ingest_data.py
│   ├── compaction_job.py
│   └── query_analysis.py
└── data/
```

### 1.2. Docker Compose Dosyası

`docker-compose.yml` oluştur:

```yaml
version: '3.8'

services:
  # HOT TIER - Primary MinIO Cluster (Distributed Mode for ILM)
  minio-hot:
    image: quay.io/minio/minio:latest
    container_name: minio-hot
    ports:
      - "9000:9000"  # API
      - "9001:9001"  # Console
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
      MINIO_ILM_SCANNER_RUN_INTERVAL: 1m
    volumes:
      - minio-hot-data1:/data1
      - minio-hot-data2:/data2
      - minio-hot-data3:/data3
      - minio-hot-data4:/data4
    command: server /data1 /data2 /data3 /data4 --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    networks:
      - iceberg-net

  # COLD TIER - Remote Tier MinIO Cluster (Distributed Mode)
  minio-cold:
    image: quay.io/minio/minio:latest
    container_name: minio-cold
    ports:
      - "9100:9000"  # API
      - "9101:9001"  # Console
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio-cold-data1:/data1
      - minio-cold-data2:/data2
      - minio-cold-data3:/data3
      - minio-cold-data4:/data4
    command: server /data1 /data2 /data3 /data4 --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    networks:
      - iceberg-net

  # MinIO Client for configuration
  minio-mc:
    image: quay.io/minio/mc:latest
    container_name: minio-mc
    depends_on:
      - minio-hot
      - minio-cold
    entrypoint: /bin/sh
    command: -c "sleep infinity"
    volumes:
      - ./scripts:/scripts
    networks:
      - iceberg-net

  # Spark Master with Iceberg support
  spark-master:
    image: apache/spark:3.5.0
    container_name: spark-master
    ports:
      - "8080:8080"  # Spark Master Web UI
      - "7077:7077"  # Spark Master
      - "4040:4040"  # Spark Application UI
    environment:
      - SPARK_NO_DAEMONIZE=true
    volumes:
      - ./jars:/opt/spark/jars/custom
      - ./scripts:/scripts
      - ./data:/data
      - ./spark-config/spark-defaults.conf:/opt/spark/conf/spark-defaults.conf
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.master.Master
    networks:
      - iceberg-net

  # Spark Worker
  spark-worker:
    image: apache/spark:3.5.0
    container_name: spark-worker
    depends_on:
      - spark-master
    environment:
      - SPARK_MASTER_URL=spark://spark-master:7077
      - SPARK_WORKER_MEMORY=4G
      - SPARK_WORKER_CORES=2
      - SPARK_NO_DAEMONIZE=true
    volumes:
      - ./jars:/opt/spark/jars/custom
      - ./scripts:/scripts
      - ./data:/data
      - ./spark-config/spark-defaults.conf:/opt/spark/conf/spark-defaults.conf
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker spark://spark-master:7077
    networks:
      - iceberg-net

networks:
  iceberg-net:
    driver: bridge

volumes:
  # MinIO HOT Distributed Volumes
  minio-hot-data1:
  minio-hot-data2:
  minio-hot-data3:
  minio-hot-data4:
  # MinIO COLD Distributed Volumes
  minio-cold-data1:
  minio-cold-data2:
  minio-cold-data3:
  minio-cold-data4:
```

**NEDEN DISTRIBUTED MODE?**
- MinIO'nun ILM scanner'ı düzgün çalışması için distributed mode gerekli
- Single mode (`server /data`) ILM'de sorunlara yol açar
- 4 disk yeterli (minimum distributed setup)

### 1.3. Spark Konfigürasyonu

`spark-config/spark-defaults.conf` oluştur:

```properties
# Spark Configuration for Iceberg + MinIO

# Iceberg Catalog Configuration
spark.sql.catalog.iceberg                              org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.type                         hadoop
spark.sql.catalog.iceberg.warehouse                    s3a://iceberg-warehouse/

# S3/MinIO Configuration
spark.hadoop.fs.s3a.endpoint                           http://minio-hot:9000
spark.hadoop.fs.s3a.access.key                         minioadmin
spark.hadoop.fs.s3a.secret.key                         minioadmin
spark.hadoop.fs.s3a.path.style.access                  true
spark.hadoop.fs.s3a.connection.ssl.enabled             false
spark.hadoop.fs.s3a.impl                               org.apache.hadoop.fs.s3a.S3AFileSystem
spark.hadoop.fs.s3a.aws.credentials.provider           org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider

# Performance tuning
spark.hadoop.fs.s3a.connection.maximum                 100
spark.hadoop.fs.s3a.fast.upload                        true
spark.hadoop.fs.s3a.multipart.size                     104857600
spark.hadoop.fs.s3a.threads.max                        20

# Iceberg Properties
spark.sql.extensions                                   org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
spark.sql.defaultCatalog                              iceberg

# Table defaults
spark.sql.iceberg.format-version                       2
spark.sql.iceberg.compression-codec                    zstd
spark.sql.iceberg.compression-level                    3

# Memory configuration
spark.executor.memory                                  2g
spark.driver.memory                                    2g

# JAR Dependencies
spark.jars                                             /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar
```

**ÖNEMLİ NOTLAR**:
- `path.style.access=true`: MinIO için gerekli (bucket-in-path style)
- `connection.ssl.enabled=false`: Test ortamı için SSL kapalı
- `compression-codec=zstd`: Yüksek sıkıştırma, hızlı
- `compression-level=3`: Dengeli (1=hızlı/düşük, 9=yavaş/yüksek)

---

## ADIM 2: Container'ları Başlatma

### 2.1. Docker Compose'u Başlat

```bash
docker-compose up -d
```

**Ne Olur?**:
- 5 container başlar: minio-hot, minio-cold, minio-mc, spark-master, spark-worker
- Docker volume'ler oluşturulur (8 volume: her minio için 4'er disk)
- Network oluşturulur: iceberg-net

### 2.2. Container Durumunu Kontrol Et

```bash
docker ps
```

**Beklenen Çıktı**:
```
CONTAINER ID   IMAGE                    STATUS                 PORTS                    NAMES
xxxxx          quay.io/minio/minio      Up (healthy)           0.0.0.0:9000->9000/tcp   minio-hot
xxxxx          quay.io/minio/minio      Up (healthy)           0.0.0.0:9100->9000/tcp   minio-cold
xxxxx          quay.io/minio/mc         Up                                              minio-mc
xxxxx          apache/spark:3.5.0       Up                     0.0.0.0:8080->8080/tcp   spark-master
xxxxx          apache/spark:3.5.0       Up                                              spark-worker
```

### 2.3. Web UI'ları Kontrol Et

- **MinIO HOT Console**: http://localhost:9001
  - Kullanıcı: minioadmin
  - Şifre: minioadmin

- **MinIO COLD Console**: http://localhost:9101
  - Kullanıcı: minioadmin
  - Şifre: minioadmin

- **Spark Master UI**: http://localhost:8080
  - Worker'ları görebilmelisiniz

---

## ADIM 3: MinIO Yapılandırması

### 3.1. Alias Yapılandırması

MinIO client (mc) için alias'lar ekle:

```bash
docker exec minio-mc mc alias set hot http://minio-hot:9000 minioadmin minioadmin
docker exec minio-mc mc alias set cold http://minio-cold:9000 minioadmin minioadmin
```

**Ne Olur?**:
- `hot` alias'ı → HOT tier'ı temsil eder
- `cold` alias'ı → COLD tier'ı temsil eder
- Sonraki komutlarda `mc ls hot` gibi kısa komutlar kullanılabilir

**Doğrulama**:
```bash
docker exec minio-mc mc alias ls
```

### 3.2. Bucket Oluşturma

HOT ve COLD tier için bucket'ları oluştur:

```bash
docker exec minio-mc mc mb hot/iceberg-warehouse
docker exec minio-mc mc mb cold/iceberg-cold-tier
```

**Açıklama**:
- `iceberg-warehouse`: Iceberg tablolarının warehouse'u (HOT)
- `iceberg-cold-tier`: Arşiv verilerinin tutulacağı bucket (COLD)

**Doğrulama**:
```bash
docker exec minio-mc mc ls hot
docker exec minio-mc mc ls cold
```

### 3.3. Tiering Yapılandırması

HOT tier'da COLD tier'ı remote tier olarak tanımla:

```bash
docker exec minio-mc mc admin tier add minio hot COLDTIER --endpoint http://minio-cold:9000 --access-key minioadmin --secret-key minioadmin --bucket iceberg-cold-tier --prefix "db/transactions/"
```

**Parametreler**:
- `minio`: Tier type (MinIO)
- `hot`: Hangi MinIO'ya tier ekliyoruz
- `COLDTIER`: Tier adı (ILM rule'larında kullanılacak)
- `--endpoint`: COLD tier URL'i
- `--bucket`: COLD tier'daki hedef bucket
- `--prefix`: COLD'a kopyalanırken eklenecek prefix (klasör yapısını korur)

**Doğrulama**:
```bash
docker exec minio-mc mc admin tier ls hot
```

**Beklenen Çıktı**:
```
COLDTIER
   Endpoint:   http://minio-cold:9000
   Bucket:     iceberg-cold-tier
   Prefix:     db/transactions/
   Status:     ready
```

### 3.4. COLD Tier'da Compression Aktif Et

COLD tier'da Parquet dosyaları için compression:

```bash
docker exec minio-mc mc admin config set cold compression enable=on extensions=".parquet" allow_encryption=off
```

**Açıklama**:
- `.parquet` uzantılı dosyalar COLD'a kopyalanırken sıkıştırılır
- Ek depolama tasarrufu sağlar

**Restart gerekli**:
```bash
docker exec minio-mc mc admin service restart cold
```

---

## ADIM 4: Iceberg Tablosu Oluşturma

### 4.1. İlk Veri Yükleme (Tablo Oluşturur)

`ingest_data.py` script'i tablo yoksa otomatik oluşturur:

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py
```

**Script Ne Yapar?**:
1. Spark session oluşturur (spark-defaults.conf'tan config'ler alır)
2. Tablo varsa kontrol, yoksa oluşturur:
   ```sql
   CREATE TABLE IF NOT EXISTS iceberg.db.transactions (
       transaction_id STRING,
       category STRING,
       region STRING,
       amount DOUBLE,
       quantity INT,
       date DATE,
       payload STRING
   )
   USING iceberg
   PARTITIONED BY (date)
   TBLPROPERTIES (
       'format-version' = '2',
       'write.format.default' = 'parquet',
       'write.parquet.compression-codec' = 'zstd',
       'write.parquet.compression-level' = '3',
       'write.target-file-size-bytes' = '134217728'
   )
   ```
3. 10,000 sample kayıt oluşturur (bugünün tarihi ile)
4. Tabloya yazar: `df.writeTo("iceberg.db.transactions").append()`
5. İstatistikleri gösterir

**Tablo Özellikleri**:
- **Partition**: `date` kolonuna göre (her gün ayrı klasör)
- **Format**: Parquet (kolonsal, sıkıştırılmış)
- **Compression**: ZSTD Level 3 (hızlı + iyi sıkıştırma)
- **Target File Size**: 128MB (134217728 bytes)

### 4.2. MinIO'da Oluşan Yapı

```bash
docker exec minio-mc mc ls --recursive hot/iceberg-warehouse/
```

**Beklenen Çıktı**:
```
hot/iceberg-warehouse/db/transactions/data/date=2025-11-02/00000-xxx.parquet
hot/iceberg-warehouse/db/transactions/metadata/00000-xxx.metadata.json
hot/iceberg-warehouse/db/transactions/metadata/snap-xxx.avro
hot/iceberg-warehouse/db/transactions/metadata/v1.metadata.json
hot/iceberg-warehouse/metadata/db.transactions/metadata.json
```

**Açıklama**:
- `data/date=YYYY-MM-DD/`: Partition klasörleri
- `*.parquet`: Gerçek veri dosyaları
- `metadata/`: Iceberg metadata dosyaları
  - `vN.metadata.json`: Tablo metadata (schema, partition, snapshot list)
  - `snap-*.avro`: Snapshot detayları (manifest list)
  - `*.avro`: Manifest files (dosya listesi)

---

# 5. VERI İŞLEMLERİ

## 5.1. Basit Veri Yazma

### Varsayılan Parametrelerle (10K kayıt, bugün)

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py
```

### Özelleştirilmiş Veri Yazma

#### Farklı Tarih İçin Veri Yazma

```bash
# 1 gün önce için veri
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --date-offset 1

# 5 gün önce için veri
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --date-offset 5
```

**`--date-offset` Parametresi**:
- `0`: Bugün (varsayılan)
- `1`: Dün
- `N`: N gün önce

#### Büyük Dosya Oluşturma (ILM Test İçin)

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --num-records 30000 --payload-bytes 4096 --compression none --disable-parquet-dictionary --repartition 8 --random-payload
```

**Parametreler**:
- `--num-records 30000`: 30K kayıt
- `--payload-bytes 4096`: Her satıra 4KB ekstra string
- `--compression none`: Sıkıştırma kapalı (büyük dosya için)
- `--disable-parquet-dictionary`: Dictionary encoding kapalı (daha büyük dosya)
- `--repartition 8`: 8 partition'a böl (8 dosya oluşur)
- `--random-payload`: Her satır için rastgele payload (daha büyük dosya)

**Sonuç**: ~100MB+ Parquet dosyaları oluşur

### Script Parametreleri Tam Liste

```
--clean                         Tabloyu sil ve yeniden oluştur
--num-records N                 Kayıt sayısı (varsayılan: 10000)
--date-offset N                 Kaç gün önce (varsayılan: 0=bugün)
--payload-bytes N               Satır başına ek payload boyutu (varsayılan: 0)
--compression CODEC             zstd|gzip|none (varsayılan: zstd)
--target-file-size-bytes N      Hedef dosya boyutu (varsayılan: 134217728=128MB)
--repartition N                 Yazmadan önce N partition'a böl
--random-payload                Rastgele payload üret
--disable-parquet-dictionary    Parquet dictionary encoding kapat
```

## 5.2. Tablo Temizleme

### Tabloyu Sil ve Yeniden Oluştur

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --clean
```

**Ne Olur?**:
1. Mevcut tablo silinir: `DROP TABLE IF EXISTS iceberg.db.transactions`
2. Tablo yeniden oluşturulur
3. Yeni veri yazılır

### Manuel Silme

**Sadece Tablo**:
```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "DROP TABLE IF EXISTS iceberg.db.transactions PURGE"
```

**PURGE**: Metadata + veri dosyaları tamamen silinir

**MinIO'dan Manuel Silme**:
```bash
# HOT'tan sil
docker exec minio-mc mc rm --recursive --force hot/iceberg-warehouse/db/

# COLD'dan sil
docker exec minio-mc mc rm --recursive --force cold/iceberg-cold-tier/db/
```

## 5.3. Tek Kayıt Ekleme (Test)

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
INSERT INTO iceberg.db.transactions VALUES
('MANUAL_20251102_000001','Electronics','West',123.45,1,DATE '2025-11-02',NULL);
"
```

---

# 6. MINIO TIERING YAPILANDIRMASI

## 6.1. ILM Rule Oluşturma

### Basit ILM Rule (1 Gün Sonra Taşı)

```bash
docker exec minio-mc mc ilm add hot/iceberg-warehouse --transition-days 1 --storage-class COLDTIER --prefix "db/transactions/data/"
```

**Parametreler**:
- `--transition-days 1`: 1 gün sonra taşı
- `--storage-class COLDTIER`: Hangi tier'a taşıyacak (daha önce tanımladık)
- `--prefix "db/transactions/data/"`: Sadece bu prefix'teki dosyalar

### Hemen Taşı (0 Gün)

```bash
docker exec minio-mc mc ilm add hot/iceberg-warehouse --transition-days 0 --storage-class COLDTIER --prefix "db/transactions/data/"
```

**Not**: MinIO saatte/dakikada transition desteklemiyor, minimum 0 gün

### Tag Bazlı ILM Rule

```bash
docker exec minio-mc mc ilm rule add hot/iceberg-warehouse --prefix "db/transactions/data/" --tags "type=backfill" --transition-days 0 --transition-tier COLDTIER
```

**Açıklama**:
- Sadece `type=backfill` tag'li objeler taşınır
- Daha granüler kontrol için

## 6.2. Object Tagging

### Tag Ekleme

```bash
# Tek dosya
docker exec minio-mc mc tag set hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/00000-xxx.parquet "type=backfill"

# Tüm partition (recursive)
docker exec minio-mc mc tag set --recursive hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/ "type=backfill"
```

**Syntax**: `mc tag set [--recursive] ALIAS/PATH "key=value"`

### Tag Görüntüleme

```bash
# Tek dosya
docker exec minio-mc mc tag list hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/00000-xxx.parquet

# Tüm partition
docker exec minio-mc mc tag list --recursive hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/
```

### Tag Silme

```bash
docker exec minio-mc mc tag remove --recursive hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/
```

**Not**: `--exclude-folders` flag'i eklemezsen folder placeholder'lar da silinir

## 6.3. ILM Rule Yönetimi

### Mevcut Rule'ları Görüntüleme

```bash
docker exec minio-mc mc ilm ls hot/iceberg-warehouse
```

**Çıktı**:
```
ID                      | Prefix                     | Status   | Transition Days | Tier
d3o1mbi10ghs01cnkg90    | db/transactions/data/      | Enabled  | 0               | COLDTIER
```

### Rule Silme

```bash
docker exec minio-mc mc ilm rm hot/iceberg-warehouse --id d3o1mbi10ghs01cnkg90
```

### Tüm Rule'ları Silme

```bash
# Önce rule ID'leri al
docker exec minio-mc mc ilm ls hot/iceberg-warehouse

# Her birini tek tek sil
docker exec minio-mc mc ilm rm hot/iceberg-warehouse --id <RULE_ID>
```

## 6.4. Tier Bilgilerini Kontrol Etme

### Tier Listesi

```bash
docker exec minio-mc mc admin tier ls hot
```

### Tier Detayları

```bash
docker exec minio-mc mc admin tier info hot COLDTIER
```

**Çıktı**:
```
Name:           COLDTIER
Type:           minio
Endpoint:       http://minio-cold:9000
Bucket:         iceberg-cold-tier
Prefix:         db/transactions/
Objects:        42        ← Kaç dosya taşınmış
Versions:       42
Size:           124.5 MiB ← Toplam boyut
```

**ÖNEMLİ**: Eğer `Objects: 0` ise ILM henüz çalışmamış veya dosyalar kriterlere uymuyor

## 6.5. ILM Çalışma Zamanı

MinIO'nun ILM scanner'ı:
- **Interval**: `MINIO_ILM_SCANNER_RUN_INTERVAL=1m` (1 dakika)
- **İlk Scan**: Container başladıktan birkaç dakika sonra
- **Kontrol**: `--transition-days` parametresine göre dosya yaşını kontrol eder

**Manuel Trigger**: Mümkün değil, sadece interval ayarı yapılabilir

---

# 7. SORGULAMA VE ANALİZ

## 7.1. Basit Sorgular

### Kayıt Sayısı

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT COUNT(*) as total_records FROM iceberg.db.transactions"
```

### Tarih Bazlı Sorgulama

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT COUNT(*) AS cnt, SUM(amount) AS total_amount
FROM iceberg.db.transactions
WHERE date = DATE '2025-10-31';
"
```

**Açıklama**:
- Iceberg otomatik olarak sadece ilgili partition'ı okur
- HOT'ta olan veya COLD'a taşınmış tüm dosyalar sorgulanır (transparent)

### Partition Özeti

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT date, COUNT(*) as record_count, ROUND(SUM(amount), 2) as total_revenue
FROM iceberg.db.transactions
GROUP BY date
ORDER BY date DESC;
"
```

## 7.2. Metadata Sorguları

### Dosya Listesi

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT file_path, file_size_in_bytes, record_count, partition
FROM iceberg.db.transactions.files;
"
```

**Açıklama**:
- Iceberg metadata'sındaki dosya listesi
- Hangi partition'da kaç dosya, ne kadar veri var

### Partition İstatistikleri

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT partition.date, file_count, ROUND(total_data_file_size_in_bytes / 1024.0 / 1024.0, 2) as size_mb, record_count
FROM iceberg.db.transactions.partitions
ORDER BY partition.date DESC;
"
```

### Snapshot Geçmişi

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT committed_at, snapshot_id, operation, summary
FROM iceberg.db.transactions.snapshots
ORDER BY committed_at DESC
LIMIT 10;
"
```

**Snapshot Operation'lar**:
- `append`: INSERT/COPY işlemi
- `replace`: Compaction, UPDATE işlemleri
- `overwrite`: TRUNCATE, full overwrite
- `delete`: DELETE işlemi

## 7.3. Time Travel

### Snapshot ID ile Geçmişe Dönük Sorgu

```bash
# Önce snapshot ID al
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT snapshot_id, committed_at FROM iceberg.db.transactions.snapshots ORDER BY committed_at DESC LIMIT 5;
"

# Belirli snapshot'tan sor
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT COUNT(*) FROM iceberg.db.transactions VERSION AS OF 1234567890123456789;
"
```

### Timestamp ile Geçmişe Dönük Sorgu

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT COUNT(*) FROM iceberg.db.transactions TIMESTAMP AS OF '2025-11-01 15:30:00';
"
```

## 7.4. Kompleks Analiz Script'i

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/query_analysis.py
```

**Script İçeriği**:
1. Temel istatistikler (günlük özet)
2. Kategori analizi (hangi kategori ne kadar sattı)
3. Bölgesel performans (region bazlı)
4. Top performanslar (en yüksek satışlar)
5. Zaman serisi analizi (günlük büyüme)
6. Percentile dağılımı (fiyat dağılımı)
7. Pivot analizi (region x category)
8. Cohort analizi (kategori trendleri)
9. Gelişmiş aggregasyonlar (ROLLUP)
10. Özel metrikler (transaction segmentation)
11. Metadata bilgileri

---

# 8. BAKIM İŞLEMLERİ

## 8.1. Compaction

### Manual Compaction

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/compaction_job.py
```

**Ne Yapar?**:
1. Belirli partition'daki küçük dosyaları birleştirir
2. **Binpack strategy**: Dosyaları 256MB hedefine göre paketler
3. Eski dosyalar "deleted" olarak işaretlenir (metadata'da)
4. Query performance artar (daha az dosya okunur)

**Örnek Çıktı**:
```
Compaction Öncesi:
  Dosya sayısı: 8
  Toplam boyut: 45.2 MB
  Ortalama dosya boyutu: 5.65 MB

Compaction Sonrası:
  Dosya sayısı: 1
  Toplam boyut: 44.8 MB
  Ortalama dosya boyutu: 44.8 MB

Compaction Sonuçları:
  Süre: 12.34 saniye
  Boyut azalması: 0.9%
  Dosya azalması: 87.5%
```

### Compaction SQL (Manual)

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CALL iceberg.system.rewrite_data_files(
    table => 'iceberg.db.transactions',
    strategy => 'binpack',
    where => \"date = DATE'2025-11-02'\",
    options => map(
        'target-file-size-bytes', '268435456',
        'rewrite-all', 'true'
    )
);
"
```

**Parametreler**:
- `strategy`: `binpack` (dosyaları birleştir) veya `sort` (sırala)
- `where`: Hangi partition
- `target-file-size-bytes`: Hedef dosya boyutu (256MB = 268435456)
- `rewrite-all`: Tüm dosyaları yeniden yaz (false: sadece küçükler)

## 8.2. Snapshot Temizleme

### Eski Snapshot'ları Sil

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CALL iceberg.system.expire_snapshots(
    table => 'iceberg.db.transactions',
    older_than => TIMESTAMP '2025-10-25 00:00:00',
    retain_last => 5
);
"
```

**Parametreler**:
- `older_than`: Bu tarihten eski snapshot'lar silinir
- `retain_last`: En son N snapshot'ı koru (silinmez)

**Ne Olur?**:
- Eski snapshot'ların metadata dosyaları silinir
- Time travel artık bu snapshot'lara erişemez

## 8.3. Orphan File Temizleme

### Orphan Dosyaları Bul ve Sil

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CALL iceberg.system.remove_orphan_files(
    table => 'iceberg.db.transactions',
    older_than => TIMESTAMP '2025-10-30 00:00:00'
);
"
```

**Orphan File Nedir?**:
- Hiçbir snapshot'ta referans edilmeyen dosyalar
- Genellikle compaction sonrası eski dosyalar
- Snapshot expire edildikten sonra orphan olurlar

**Güvenlik**: `older_than` kullan (yeni orphan'lar başka bir işlemin parçası olabilir)

## 8.4. Cron ile Otomatik Bakım

### Crontab Örneği (Linux/Mac)

```bash
# Her gece 23:00'da compaction
0 23 * * * docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/compaction_job.py

# Her hafta Pazar 02:00'da snapshot temizleme
0 2 * * 0 docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "CALL iceberg.system.expire_snapshots(...)"

# Her hafta Pazar 03:00'da orphan temizleme
0 3 * * 0 docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "CALL iceberg.system.remove_orphan_files(...)"
```

### Windows Task Scheduler

PowerShell script oluştur (`maintenance.ps1`):

```powershell
# Compaction
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/compaction_job.py

# Snapshot temizleme
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "CALL iceberg.system.expire_snapshots(...)"
```

Task Scheduler'da günlük/haftalık görev oluştur.

---

# 9. SORUN GİDERME

## 9.1. ILM Çalışmıyor

**Semptom**: `mc admin tier info hot COLDTIER` → `Objects: 0`

**Olası Nedenler**:
1. **MinIO Single Mode**: Distributed mode gerekli
   - Kontrol: `docker exec minio-hot minio --version`
   - docker-compose.yml'de: `server /data1 /data2 /data3 /data4`

2. **ILM Rule Yok veya Yanlış**:
   ```bash
   docker exec minio-mc mc ilm ls hot/iceberg-warehouse
   ```
   - Rule prefix'i doğru mu? → `db/transactions/data/`
   - transition-days doğru mu?

3. **Dosyalar Henüz Yaşlanmadı**:
   - `--transition-days 1` → Dosya 1 günlük olmalı
   - Dosya creation time kontrol: `mc stat`

4. **ILM Scanner Çalışmıyor**:
   - Container loglarına bak: `docker logs minio-hot`
   - Scanner interval: `MINIO_ILM_SCANNER_RUN_INTERVAL=1m`

**Çözüm**:
```bash
# Distributed mode'u kontrol et
docker exec minio-hot minio server /data1 /data2 /data3 /data4

# ILM rule yeniden ekle
docker exec minio-mc mc ilm rm hot/iceberg-warehouse --id <OLD_ID>
docker exec minio-mc mc ilm add hot/iceberg-warehouse --transition-days 0 --storage-class COLDTIER --prefix "db/transactions/data/"

# Container restart
docker restart minio-hot
```

## 9.2. Spark MinIO'ya Bağlanamıyor

**Semptom**: `Connection refused: minio-hot:9000`

**Olası Nedenler**:
1. **Network Sorunu**: Container'lar aynı network'te mi?
   ```bash
   docker network inspect iceberg-net
   ```

2. **MinIO Başlamamış**: Health check geçiyor mu?
   ```bash
   docker ps
   ```
   - `(healthy)` yazıyor olmalı

3. **Yanlış Endpoint**:
   - spark-defaults.conf'ta: `http://minio-hot:9000` (container name)
   - Değil: `http://localhost:9000`

**Çözüm**:
```bash
# Network kontrol
docker network inspect iceberg-net

# MinIO restart
docker restart minio-hot

# Spark restart
docker restart spark-master spark-worker
```

## 9.3. Iceberg Tablosu Bulunamıyor

**Semptom**: `Table not found: iceberg.db.transactions`

**Olası Nedenler**:
1. **Tablo Oluşmamış**:
   ```bash
   docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SHOW TABLES IN iceberg.db"
   ```

2. **Warehouse Path Yanlış**:
   - spark-defaults.conf: `s3a://iceberg-warehouse/`
   - Bucket var mı? `mc ls hot`

3. **Catalog Konfigürasyonu Yanlış**:
   ```bash
   docker exec spark-master cat /opt/spark/conf/spark-defaults.conf
   ```

**Çözüm**:
```bash
# Tabloyu oluştur
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --clean
```

## 9.4. JAR Dosyası Bulunamıyor

**Semptom**: `ClassNotFoundException: org.apache.iceberg.spark.SparkCatalog`

**Olası Nedenler**:
1. **JAR Dosyaları Eksik**: `jars/` klasöründe 3 JAR var mı?
   ```bash
   ls -lh jars/
   ```

2. **Volume Mount Yanlış**:
   ```bash
   docker exec spark-master ls -lh /opt/spark/jars/custom/
   ```

3. **spark-defaults.conf'ta JAR Yolu Yanlış**:
   ```bash
   docker exec spark-master cat /opt/spark/conf/spark-defaults.conf | grep spark.jars
   ```

**Çözüm**:
```bash
# JAR'ları indir (Maven Central'dan)
cd jars/

wget https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.2/iceberg-spark-runtime-3.5_2.12-1.5.2.jar

wget https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar

wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar

# Container restart
docker restart spark-master spark-worker
```

## 9.5. COLD'a Taşınan Dosya HOT'tan Silinmiyor

**Semptom**: HOT ve COLD'da aynı dosya var, boyutları aynı

**Açıklama**:
- **MinIO Transparent Tiering**: HOT'ta küçük stub kalır, COLD'da gerçek veri
- Eğer iki tarafta da TAM boyut varsa → Manuel kopyalama olmuş (ILM değil)

**Doğrulama**:
```bash
# HOT'ta küçük stub mu?
docker exec minio-mc mc du hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/

# COLD'da tam dosya mı?
docker exec minio-mc mc du cold/iceberg-cold-tier/db/transactions/data/date=2025-10-31/
```

**Çözüm**:
- ILM rule düzgün çalışıyorsa HOT'ta stub kalır (birkaç KB)
- Manuel kopyalama yaptıysan iki tarafı da temizle ve ILM'e bırak

---

# 10. KOMUT REFERANSI

## 10.1. Docker Compose Komutları

```bash
# Tüm servisleri başlat
docker-compose up -d

# Servisleri durdur
docker-compose down

# Servisleri durdur ve volume'leri sil
docker-compose down -v

# Loglara bak
docker-compose logs -f

# Belirli servisin logları
docker-compose logs -f spark-master

# Servisleri restart
docker-compose restart

# Container durumu
docker-compose ps
```

## 10.2. MinIO Client (mc) Komutları

### Alias Yönetimi

```bash
# Alias ekle
docker exec minio-mc mc alias set hot http://minio-hot:9000 minioadmin minioadmin

# Alias listesi
docker exec minio-mc mc alias ls

# Alias sil
docker exec minio-mc mc alias rm hot
```

### Bucket İşlemleri

```bash
# Bucket oluştur
docker exec minio-mc mc mb hot/iceberg-warehouse

# Bucket listele
docker exec minio-mc mc ls hot

# Bucket sil
docker exec minio-mc mc rb --force hot/iceberg-warehouse

# Bucket içeriği
docker exec minio-mc mc ls --recursive hot/iceberg-warehouse/
```

### Dosya İşlemleri

```bash
# Dosya listele
docker exec minio-mc mc ls hot/iceberg-warehouse/db/transactions/data/

# Recursive listele
docker exec minio-mc mc ls --recursive hot/iceberg-warehouse/

# Dosya boyutu
docker exec minio-mc mc du hot/iceberg-warehouse/db/transactions/

# Recursive boyut
docker exec minio-mc mc du -r hot/iceberg-warehouse/

# Dosya detayları
docker exec minio-mc mc stat hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/00000-xxx.parquet

# Dosya kopyala
docker exec minio-mc mc cp hot/iceberg-warehouse/file.txt cold/iceberg-cold-tier/

# Dosya sil
docker exec minio-mc mc rm hot/iceberg-warehouse/file.txt

# Recursive sil
docker exec minio-mc mc rm --recursive --force hot/iceberg-warehouse/db/
```

### Tiering Komutları

```bash
# Tier ekle
docker exec minio-mc mc admin tier add minio hot COLDTIER --endpoint http://minio-cold:9000 --access-key minioadmin --secret-key minioadmin --bucket iceberg-cold-tier --prefix "db/transactions/"

# Tier listele
docker exec minio-mc mc admin tier ls hot

# Tier detayları
docker exec minio-mc mc admin tier info hot COLDTIER

# Tier sil
docker exec minio-mc mc admin tier rm hot COLDTIER
```

### ILM Komutları

```bash
# ILM rule ekle
docker exec minio-mc mc ilm add hot/iceberg-warehouse --transition-days 1 --storage-class COLDTIER --prefix "db/transactions/data/"

# ILM rule listele
docker exec minio-mc mc ilm ls hot/iceberg-warehouse

# ILM rule sil
docker exec minio-mc mc ilm rm hot/iceberg-warehouse --id <RULE_ID>

# Tag bazlı ILM
docker exec minio-mc mc ilm rule add hot/iceberg-warehouse --prefix "db/transactions/data/" --tags "type=backfill" --transition-days 0 --transition-tier COLDTIER
```

### Tag Komutları

```bash
# Tag ekle (tek dosya)
docker exec minio-mc mc tag set hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/00000-xxx.parquet "type=backfill"

# Tag ekle (recursive)
docker exec minio-mc mc tag set --recursive hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/ "type=backfill"

# Tag listele
docker exec minio-mc mc tag list hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/00000-xxx.parquet

# Tag sil
docker exec minio-mc mc tag remove --recursive hot/iceberg-warehouse/db/transactions/data/date=2025-10-31/
```

### Admin Komutları

```bash
# Config görüntüle
docker exec minio-mc mc admin config get hot

# Config ayarla
docker exec minio-mc mc admin config set cold compression enable=on extensions=".parquet"

# Servis restart
docker exec minio-mc mc admin service restart cold

# Server bilgisi
docker exec minio-mc mc admin info hot
```

## 10.3. Spark Komutları

### Spark SQL (İnteraktif)

```bash
# Spark SQL shell başlat
docker exec -it spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077
```

### Spark SQL (Tek Sorgu)

```bash
# Basit sorgu
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT COUNT(*) FROM iceberg.db.transactions"

# Kompleks sorgu
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT date, COUNT(*) as cnt, SUM(amount) as total
FROM iceberg.db.transactions
GROUP BY date
ORDER BY date DESC;
"
```

### Spark Submit (Python Script)

```bash
# Veri ingestion
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py

# Parametreli
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --num-records 30000 --date-offset 1

# Compaction
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/compaction_job.py

# Query analysis
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/query_analysis.py
```

### Iceberg System Procedures

```bash
# Compaction (binpack)
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CALL iceberg.system.rewrite_data_files(
    table => 'iceberg.db.transactions',
    strategy => 'binpack',
    where => \"date = DATE'2025-11-02'\",
    options => map('target-file-size-bytes', '268435456')
);
"

# Snapshot expire
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CALL iceberg.system.expire_snapshots(
    table => 'iceberg.db.transactions',
    older_than => TIMESTAMP '2025-10-25 00:00:00',
    retain_last => 5
);
"

# Orphan files cleanup
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CALL iceberg.system.remove_orphan_files(
    table => 'iceberg.db.transactions',
    older_than => TIMESTAMP '2025-10-30 00:00:00'
);
"

# Snapshot rollback
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CALL iceberg.system.rollback_to_snapshot(
    table => 'iceberg.db.transactions',
    snapshot_id => 1234567890123456789
);
"
```

### Iceberg Metadata Queries

```bash
# Dosya listesi
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT * FROM iceberg.db.transactions.files"

# Partition listesi
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT * FROM iceberg.db.transactions.partitions"

# Snapshot listesi
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT * FROM iceberg.db.transactions.snapshots"

# Manifest listesi
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT * FROM iceberg.db.transactions.manifests"

# History
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT * FROM iceberg.db.transactions.history"
```

## 10.4. Table DDL Komutları

```bash
# Tablo oluştur
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
CREATE TABLE iceberg.db.transactions (
    transaction_id STRING,
    category STRING,
    region STRING,
    amount DOUBLE,
    quantity INT,
    date DATE,
    payload STRING
)
USING iceberg
PARTITIONED BY (date)
TBLPROPERTIES (
    'format-version' = '2',
    'write.format.default' = 'parquet',
    'write.parquet.compression-codec' = 'zstd',
    'write.parquet.compression-level' = '3'
)
"

# Tablo sil
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "DROP TABLE IF EXISTS iceberg.db.transactions PURGE"

# Tablo listesi
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SHOW TABLES IN iceberg.db"

# Tablo şeması
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "DESCRIBE EXTENDED iceberg.db.transactions"

# Tablo özellikleri değiştir
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
ALTER TABLE iceberg.db.transactions SET TBLPROPERTIES (
  'write.parquet.compression-codec' = 'gzip'
)
"
```

## 10.5. DML Komutları

```bash
# INSERT
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
INSERT INTO iceberg.db.transactions VALUES
('TXN001','Electronics','West',123.45,1,DATE '2025-11-02',NULL)
"

# SELECT
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT * FROM iceberg.db.transactions WHERE date = DATE '2025-11-02' LIMIT 10
"

# UPDATE
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
UPDATE iceberg.db.transactions
SET amount = amount * 1.1
WHERE category = 'Electronics'
"

# DELETE
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
DELETE FROM iceberg.db.transactions
WHERE date < DATE '2025-10-01'
"

# MERGE (UPSERT)
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
MERGE INTO iceberg.db.transactions t
USING (SELECT 'TXN001' as transaction_id, 999.99 as amount) s
ON t.transaction_id = s.transaction_id
WHEN MATCHED THEN UPDATE SET t.amount = s.amount
WHEN NOT MATCHED THEN INSERT *
"
```

## 10.6. Time Travel Komutları

```bash
# Timestamp ile
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT COUNT(*) FROM iceberg.db.transactions TIMESTAMP AS OF '2025-11-01 15:30:00'
"

# Snapshot ID ile
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT COUNT(*) FROM iceberg.db.transactions VERSION AS OF 1234567890123456789
"

# Snapshot karşılaştırma
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "
SELECT 
  (SELECT COUNT(*) FROM iceberg.db.transactions VERSION AS OF 111) as before_count,
  (SELECT COUNT(*) FROM iceberg.db.transactions VERSION AS OF 222) as after_count
"
```

---

# 11. SADE KOMUTLAR (COPY-PASTE İÇİN)

## Kurulum Komutları

```bash
docker-compose up -d
docker exec minio-mc mc alias set hot http://minio-hot:9000 minioadmin minioadmin
docker exec minio-mc mc alias set cold http://minio-cold:9000 minioadmin minioadmin
docker exec minio-mc mc mb hot/iceberg-warehouse
docker exec minio-mc mc mb cold/iceberg-cold-tier
docker exec minio-mc mc admin tier add minio hot COLDTIER --endpoint http://minio-cold:9000 --access-key minioadmin --secret-key minioadmin --bucket iceberg-cold-tier --prefix "db/transactions/"
docker exec minio-mc mc admin config set cold compression enable=on extensions=".parquet" allow_encryption=off
docker exec minio-mc mc admin service restart cold
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py
```

## ILM Yapılandırması

```bash
docker exec minio-mc mc ilm add hot/iceberg-warehouse --transition-days 0 --storage-class COLDTIER --prefix "db/transactions/data/"
docker exec minio-mc mc ilm ls hot/iceberg-warehouse
docker exec minio-mc mc admin tier info hot COLDTIER
```

## Veri İşlemleri

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --num-records 30000 --date-offset 1
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py --clean
```

## Sorgulama

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT COUNT(*) FROM iceberg.db.transactions"
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT date, COUNT(*) as cnt FROM iceberg.db.transactions GROUP BY date ORDER BY date DESC"
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/query_analysis.py
```

## Bakım

```bash
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/compaction_job.py
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "CALL iceberg.system.expire_snapshots(table => 'iceberg.db.transactions', older_than => TIMESTAMP '2025-10-25 00:00:00', retain_last => 5)"
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "CALL iceberg.system.remove_orphan_files(table => 'iceberg.db.transactions', older_than => TIMESTAMP '2025-10-30 00:00:00')"
```

## Monitoring

```bash
docker exec minio-mc mc ls --recursive hot/iceberg-warehouse/
docker exec minio-mc mc ls --recursive cold/iceberg-cold-tier/
docker exec minio-mc mc du -r hot/iceberg-warehouse/
docker exec minio-mc mc du -r cold/iceberg-cold-tier/
docker exec minio-mc mc admin tier info hot COLDTIER
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT * FROM iceberg.db.transactions.files"
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "SELECT * FROM iceberg.db.transactions.snapshots"
```

## Temizlik

```bash
docker exec spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 -e "DROP TABLE IF EXISTS iceberg.db.transactions PURGE"
docker exec minio-mc mc rm --recursive --force hot/iceberg-warehouse/db/
docker exec minio-mc mc rm --recursive --force cold/iceberg-cold-tier/db/
docker-compose down -v
```

---

# 12. ÖZET: NELER YAPTIK?

## Teknoloji Stack

1. **MinIO (2 adet)**:
   - HOT tier: Sık erişilen veriler
   - COLD tier: Arşiv verileri
   - Distributed mode: ILM desteği için
   - Transparent tiering: Kullanıcı fark etmez

2. **Apache Spark**:
   - Master + Worker cluster
   - PySpark ile Python script desteği
   - SQL engine ile interaktif sorgulama

3. **Apache Iceberg**:
   - Modern table format
   - ACID transactions
   - Time travel (snapshot bazlı)
   - Schema evolution
   - Hidden partitioning

4. **Hadoop S3A FileSystem**:
   - MinIO'ya S3 protokolü ile erişim
   - Credential yönetimi
   - Performance optimizasyonları

## Veri Akışı

```
1. Veri Yazma:
   Python Script → Spark → Iceberg → S3A → MinIO HOT

2. ILM Tiering:
   MinIO ILM Scanner → Rule Evaluation → HOT → COLD (transparent)

3. Sorgulama:
   SQL Query → Spark → Iceberg Metadata → Read Files (HOT+COLD) → Results
```

## Oluşturduğumuz Altyapı

- **5 Container**: minio-hot, minio-cold, minio-mc, spark-master, spark-worker
- **8 Volume**: Her MinIO için 4'er distributed disk
- **1 Network**: iceberg-net (bridge)
- **3 JAR**: Iceberg, AWS SDK, Hadoop-AWS
- **1 Spark Config**: spark-defaults.conf
- **3 Python Script**: ingest_data.py, compaction_job.py, query_analysis.py
- **1 Iceberg Table**: transactions (date partitioned, ZSTD compressed)
- **2 Bucket**: iceberg-warehouse (HOT), iceberg-cold-tier (COLD)
- **1 Remote Tier**: COLDTIER
- **N ILM Rule**: Otomatik tiering için

## Başardığımız Özellikler

✅ Hot/Cold tiering altyapısı
✅ Otomatik ILM ile veri yaşam döngüsü
✅ Iceberg ile ACID transactions
✅ Time travel (geçmişe dönük sorgulama)
✅ Partition bazlı query optimization
✅ ZSTD compression ile depolama tasarrufu
✅ Compaction ile query performance
✅ Snapshot yönetimi
✅ Orphan file cleanup
✅ Transparent tiering (kullanıcı fark etmez)
✅ Python ve SQL ile veri yönetimi

---

# SON NOTLAR

Bu dokümantasyon, sıfırdan 100'e tüm sistem kurulumunu ve kullanımını içermektedir.

**Üretim Ortamına Geçiş İçin**:
- MinIO için production-grade distributed setup (8+ node)
- Spark cluster scaling (multiple workers)
- Security: SSL/TLS, IAM, encryption
- Monitoring: Prometheus + Grafana
- Backup strategy
- Disaster recovery plan

**İletişim ve Destek**:
- Apache Iceberg: https://iceberg.apache.org
- MinIO Docs: https://min.io/docs
- Spark Docs: https://spark.apache.org/docs

---

**DOKÜMANTASYON SONU**

