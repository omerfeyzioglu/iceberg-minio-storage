# 🚀 Apache Iceberg + MinIO Multi-Tier Storage - Hızlı Kurulum

**Yeni Bilgisayara Sıfırdan Kurulum Kılavuzu**

Bu dosyadaki her komutu sırayla kopyala-yapıştır yaparak çalıştır.

---

## 📋 Gereksinimler

- ✅ Windows 10/11
- ✅ Docker Desktop (çalışır durumda)
- ✅ PowerShell
- ✅ İnternet bağlantısı

---

## 🏗️ ADIM 1: Proje Klasörü Oluştur

```powershell
# Proje klasörü oluştur
mkdir iceberg-minio-tiering
cd iceberg-minio-tiering

# Alt klasörleri oluştur
mkdir jars, data, scripts, spark-config
```

---

## 📦 ADIM 2: docker-compose.yml Oluştur

**Dosya:** `docker-compose.yml`

```yaml
version: '3.8'

networks:
  iceberg-net:
    driver: bridge

services:
  # HOT Tier MinIO
  minio-hot:
    image: quay.io/minio/minio:latest
    container_name: minio-hot
    ports:
      - "9000:9000"  # API
      - "9001:9001"  # Web UI
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - ./data/minio-hot:/data
    command: server /data --console-address ":9001"
    networks:
      - iceberg-net
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 5

  # COLD Tier MinIO
  minio-cold:
    image: quay.io/minio/minio:latest
    container_name: minio-cold
    ports:
      - "9100:9000"  # API
      - "9101:9001"  # Web UI
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - ./data/minio-cold:/data
    command: server /data --console-address ":9001"
    networks:
      - iceberg-net
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 5

  # MinIO Client
  minio-mc:
    image: quay.io/minio/mc:latest
    container_name: minio-mc
    depends_on:
      - minio-hot
      - minio-cold
    entrypoint: >
      /bin/sh -c "
      sleep infinity
      "
    volumes:
      - ./scripts:/scripts
    networks:
      - iceberg-net

  # Spark Master
  spark-master:
    image: apache/spark:3.5.0
    container_name: spark-master
    ports:
      - "8081:8080"  # Spark Master Web UI
      - "7077:7077"  # Spark Master
      - "4041:4040"  # Spark Application UI
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
      - SPARK_MASTER=spark://spark-master:7077
      - SPARK_WORKER_CORES=2
      - SPARK_WORKER_MEMORY=2G
      - SPARK_NO_DAEMONIZE=true
    volumes:
      - ./jars:/opt/spark/jars/custom
      - ./scripts:/scripts
      - ./data:/data
      - ./spark-config/spark-defaults.conf:/opt/spark/conf/spark-defaults.conf
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker spark://spark-master:7077
    networks:
      - iceberg-net
```

---

## 📥 ADIM 3: JAR Dosyalarını İndir

**Dosya:** `scripts/download-jars.sh`

```bash
#!/bin/bash
mkdir -p jars

# 1. Iceberg
echo "📥 Iceberg Spark Runtime indiriliyor..."
curl -L "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.2/iceberg-spark-runtime-3.5_2.12-1.5.2.jar" \
  -o "jars/iceberg-spark-runtime-3.5_2.12-1.5.2.jar"

# 2. AWS SDK
echo "📥 AWS Java SDK Bundle indiriliyor..."
curl -L "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar" \
  -o "jars/aws-java-sdk-bundle-1.12.262.jar"

# 3. Hadoop AWS
echo "📥 Hadoop AWS indiriliyor..."
curl -L "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar" \
  -o "jars/hadoop-aws-3.3.4.jar"

echo "✅ Tüm JAR'lar indirildi!"
ls -lh jars/
```

**PowerShell'de çalıştır:**
```powershell
# Git Bash kullanarak
bash scripts/download-jars.sh

# VEYA manuel indir (Windows):
Invoke-WebRequest -Uri "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.2/iceberg-spark-runtime-3.5_2.12-1.5.2.jar" -OutFile "jars/iceberg-spark-runtime-3.5_2.12-1.5.2.jar"

Invoke-WebRequest -Uri "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar" -OutFile "jars/aws-java-sdk-bundle-1.12.262.jar"

Invoke-WebRequest -Uri "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar" -OutFile "jars/hadoop-aws-3.3.4.jar"
```

---

## ⚙️ ADIM 4: Spark Config Oluştur

**Dosya:** `spark-config/spark-defaults.conf`

```properties
# Iceberg Catalog Configuration
spark.sql.catalog.iceberg                              org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.type                         hadoop
spark.sql.catalog.iceberg.warehouse                    s3a://iceberg-warehouse/

# MinIO (S3) Connection
spark.hadoop.fs.s3a.endpoint                           http://minio-hot:9000
spark.hadoop.fs.s3a.access.key                         minioadmin
spark.hadoop.fs.s3a.secret.key                         minioadmin
spark.hadoop.fs.s3a.path.style.access                  true
spark.hadoop.fs.s3a.connection.ssl.enabled             false
spark.hadoop.fs.s3a.impl                               org.apache.hadoop.fs.s3a.S3AFileSystem

# Iceberg Extensions
spark.sql.extensions                                   org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
spark.sql.defaultCatalog                               iceberg

# JAR Dependencies
spark.jars                                             /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar

# Performance Tuning
spark.sql.adaptive.enabled                             true
spark.sql.adaptive.coalescePartitions.enabled          true
```

---

## 🐳 ADIM 5: Docker Container'ları Başlat

```powershell
# Container'ları başlat
docker-compose up -d

# Durumu kontrol et (hepsi "healthy" olmalı)
docker-compose ps

# Logları kontrol et
docker logs minio-hot
docker logs spark-master
```

---

## 🪣 ADIM 6: MinIO Setup

**Dosya:** `scripts/setup-minio.sh`

```bash
#!/bin/bash

echo "🔧 MinIO Kurulumu Başlatılıyor..."

# Alias'ları ayarla
mc alias set hot http://minio-hot:9000 minioadmin minioadmin
mc alias set cold http://minio-cold:9000 minioadmin minioadmin

# HOT bucket'ları oluştur
mc mb hot/iceberg-metadata --ignore-existing
mc mb hot/iceberg-warehouse --ignore-existing

# COLD bucket oluştur
mc mb cold/iceberg-cold-tier --ignore-existing

# Remote tier ekle (önce kontrol et)
if mc admin tier ls hot | grep -q "COLDTIER"; then
    echo "⚠️  COLDTIER zaten var, siliniyor..."
    mc admin tier rm hot COLDTIER
fi

echo "➕ COLDTIER ekleniyor..."
mc admin tier add minio hot COLDTIER \
  --endpoint http://minio-cold:9000 \
  --access-key minioadmin \
  --secret-key minioadmin \
  --bucket iceberg-cold-tier

echo "✅ MinIO kurulumu tamamlandı!"
mc admin tier ls hot
```

**PowerShell'de çalıştır:**
```powershell
docker exec minio-mc bash /scripts/setup-minio.sh
```

**Kontrol et:**
```powershell
docker exec minio-mc mc ls hot/
docker exec minio-mc mc ls cold/
docker exec minio-mc mc admin tier ls hot
```

---

## 📊 ADIM 7: Iceberg Tablosu ve Veri Oluştur

**Dosya:** `scripts/ingest_data.py`

```python
#!/usr/bin/env python3
"""
Iceberg Veri Ingestion Script
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from datetime import datetime, timedelta
import random

def create_spark_session():
    """Spark session oluştur"""
    return SparkSession.builder \
        .appName("Iceberg Data Ingestion") \
        .config("spark.jars", "/opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,"
                              "/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,"
                              "/opt/spark/jars/custom/hadoop-aws-3.3.4.jar") \
        .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.iceberg.type", "hadoop") \
        .config("spark.sql.catalog.iceberg.warehouse", "s3a://iceberg-warehouse/") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio-hot:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.defaultCatalog", "iceberg") \
        .getOrCreate()

def create_table(spark):
    """Iceberg tablosu oluştur"""
    print("\n🗂️ Tablo oluşturuluyor...")
    
    spark.sql("""
        CREATE DATABASE IF NOT EXISTS iceberg.db
    """)
    
    spark.sql("""
        CREATE TABLE IF NOT EXISTS iceberg.db.transactions (
            transaction_id STRING,
            user_id STRING,
            amount DOUBLE,
            category STRING,
            timestamp TIMESTAMP,
            date DATE
        )
        USING iceberg
        PARTITIONED BY (date)
        TBLPROPERTIES (
            'format-version' = '2',
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'zstd',
            'write.parquet.compression-level' = '3'
        )
    """)
    
    print("✅ Tablo oluşturuldu!")

def generate_data(spark, date, record_count):
    """Test verisi oluştur"""
    print(f"\n📝 {date} için {record_count} kayıt oluşturuluyor...")
    
    categories = ["food", "transport", "entertainment", "shopping", "utilities"]
    
    data = []
    for i in range(record_count):
        data.append({
            "transaction_id": f"TRX-{date}-{i:06d}",
            "user_id": f"USER-{random.randint(1, 1000):04d}",
            "amount": round(random.uniform(10, 1000), 2),
            "category": random.choice(categories),
            "timestamp": datetime.combine(date, datetime.min.time()) + timedelta(seconds=random.randint(0, 86400)),
            "date": date
        })
    
    df = spark.createDataFrame(data)
    return df

def ingest_data(spark):
    """Veri yaz"""
    print("\n🚀 Veri ingestion başlatılıyor...")
    
    # 3 günlük veri
    dates = [
        (datetime.now().date() - timedelta(days=2), 6000),
        (datetime.now().date() - timedelta(days=1), 8000),
        (datetime.now().date(), 10000)
    ]
    
    for date, count in dates:
        df = generate_data(spark, date, count)
        
        print(f"💾 {date} verisi yazılıyor...")
        df.writeTo("iceberg.db.transactions").append()
        print(f"✅ {date} tamamlandı!")
    
    print("\n✅ Tüm veri ingestion tamamlandı!")

def show_stats(spark):
    """İstatistikleri göster"""
    print("\n📊 Tablo İstatistikleri:")
    
    spark.sql("""
        SELECT 
            date,
            COUNT(*) as record_count,
            ROUND(SUM(amount), 2) as total_amount
        FROM iceberg.db.transactions
        GROUP BY date
        ORDER BY date
    """).show()
    
    print("\n📁 Dosya Detayları:")
    spark.sql("""
        SELECT 
            partition.date,
            file_path,
            record_count,
            ROUND(file_size_in_bytes/1024, 2) as size_kb
        FROM iceberg.db.transactions.files
        ORDER BY partition.date
    """).show(truncate=False)

def main():
    print("=" * 70)
    print("🔄 ICEBERG DATA INGESTION")
    print("=" * 70)
    
    spark = create_spark_session()
    
    try:
        create_table(spark)
        ingest_data(spark)
        show_stats(spark)
        
        print("\n" + "=" * 70)
        print("✅ İşlem Başarılı!")
        print("=" * 70)
        
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
```

**Çalıştır:**
```powershell
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar /scripts/ingest_data.py
```

---

## 🔍 ADIM 8: Veriyi Sorgula

```powershell
# Tüm veriyi göster
docker exec -it spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.iceberg.type=hadoop --conf spark.sql.catalog.iceberg.warehouse=s3a://iceberg-warehouse/ --conf spark.hadoop.fs.s3a.endpoint=http://minio-hot:9000 --conf spark.hadoop.fs.s3a.access.key=minioadmin --conf spark.hadoop.fs.s3a.secret.key=minioadmin --conf spark.hadoop.fs.s3a.path.style.access=true --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions -e "SELECT date, COUNT(*) FROM iceberg.db.transactions GROUP BY date ORDER BY date"
```

---

## 🔄 ADIM 9: Manuel Tiering Script

**Dosya:** `scripts/tiering_job.py`

```python
#!/usr/bin/env python3
"""
MinIO HOT → COLD Manuel Tiering Script
"""
import subprocess
import sys
from datetime import datetime, timedelta
import argparse
import json

class MinIOTieringManager:
    def __init__(self, age_days=1, dry_run=False):
        self.age_days = age_days
        self.dry_run = dry_run
        self.hot_alias = "hot"
        self.cold_alias = "cold"
        self.hot_bucket = "iceberg-warehouse"
        self.cold_bucket = "iceberg-cold-tier"
        self.data_prefix = "db/transactions/data/"
    
    def run_mc_command(self, command):
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"❌ Hata: {e.stderr}")
            return None
    
    def get_cutoff_date(self):
        cutoff = datetime.now() - timedelta(days=self.age_days)
        return cutoff.date()
    
    def list_hot_files(self):
        print(f"📋 HOT tier dosyaları taranıyor...")
        command = f"mc ls --recursive --json {self.hot_alias}/{self.hot_bucket}/{self.data_prefix}"
        output = self.run_mc_command(command)
        
        if not output:
            return []
        
        files = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get('type') == 'file':
                    files.append({'key': obj['key'], 'size': obj['size'], 'lastModified': obj['lastModified']})
            except json.JSONDecodeError:
                continue
        
        return files
    
    def parse_partition_from_path(self, path):
        try:
            if 'date=' in path:
                date_str = path.split('date=')[1].split('/')[0]
                return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            pass
        return None
    
    def filter_old_files(self, files):
        cutoff = self.get_cutoff_date()
        print(f"📅 Cutoff tarihi: {cutoff}")
        
        old_files = []
        for file in files:
            partition_date = self.parse_partition_from_path(file['key'])
            if partition_date and partition_date < cutoff:
                old_files.append(file)
        
        return old_files
    
    def check_already_in_cold(self, file_key):
        cold_key = file_key.replace(self.data_prefix, 'data/')
        command = f"mc stat {self.cold_alias}/{self.cold_bucket}/{cold_key} 2>/dev/null"
        result = self.run_mc_command(command)
        return result is not None and len(result) > 0
    
    def copy_to_cold(self, file_key):
        hot_path = f"{self.hot_alias}/{self.hot_bucket}/{file_key}"
        cold_key = file_key.replace(self.data_prefix, 'data/')
        cold_path = f"{self.cold_alias}/{self.cold_bucket}/{cold_key}"
        
        print(f"   📤 Kopyalanıyor: {hot_path} → {cold_path}")
        
        if self.dry_run:
            print("   🔸 DRY RUN - Gerçek kopyalama yapılmadı")
            return True
        
        command = f"mc cp {hot_path} {cold_path}"
        result = self.run_mc_command(command)
        
        if result:
            print(f"   ✅ Başarılı")
            return True
        else:
            print(f"   ❌ Başarısız")
            return False
    
    def run(self):
        print("=" * 70)
        print("🔄 MinIO Manual Tiering")
        print("=" * 70)
        print(f"⚙️  Age: {self.age_days} gün | Dry run: {self.dry_run}")
        print()
        
        all_files = self.list_hot_files()
        print(f"📊 Toplam {len(all_files)} dosya\n")
        
        if not all_files:
            print("ℹ️  Taşınacak dosya yok")
            return
        
        old_files = self.filter_old_files(all_files)
        print(f"🔍 {len(old_files)} eski dosya\n")
        
        if not old_files:
            print("✅ Taşınacak dosya yok")
            return
        
        success_count = 0
        skip_count = 0
        
        for i, file in enumerate(old_files, 1):
            partition = self.parse_partition_from_path(file['key'])
            print(f"[{i}/{len(old_files)}] Partition: {partition}")
            
            if self.check_already_in_cold(file['key']):
                print(f"   ⏭️  Zaten COLD'da")
                skip_count += 1
                continue
            
            if self.copy_to_cold(file['key']):
                success_count += 1
        
        print("\n" + "=" * 70)
        print(f"✅ Başarılı: {success_count} | ⏭️ Atlandı: {skip_count}")
        print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="MinIO HOT → COLD tiering")
    parser.add_argument('--age-days', type=int, default=1, help='Kaç günden eski (default: 1)')
    parser.add_argument('--no-dry-run', action='store_true', help='Gerçek transfer')
    
    args = parser.parse_args()
    
    manager = MinIOTieringManager(age_days=args.age_days, dry_run=not args.no_dry_run)
    manager.run()

if __name__ == "__main__":
    main()
```

**Test et (Dry Run):**
```powershell
docker exec minio-mc python3 /scripts/tiering_job.py --age-days 1
```

**Gerçek Transfer:**
```powershell
docker exec minio-mc python3 /scripts/tiering_job.py --age-days 1 --no-dry-run
```

---

## 🎯 ADIM 10: Kontrol Komutları

```powershell
# MinIO HOT bucket'ları
docker exec minio-mc mc ls hot/

# MinIO COLD bucket
docker exec minio-mc mc ls --recursive cold/iceberg-cold-tier/

# Iceberg snapshots
docker exec -it spark-master /opt/spark/bin/spark-sql --master spark://spark-master:7077 --jars /opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/custom/hadoop-aws-3.3.4.jar --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.iceberg.type=hadoop --conf spark.sql.catalog.iceberg.warehouse=s3a://iceberg-warehouse/ --conf spark.hadoop.fs.s3a.endpoint=http://minio-hot:9000 --conf spark.hadoop.fs.s3a.access.key=minioadmin --conf spark.hadoop.fs.s3a.secret.key=minioadmin --conf spark.hadoop.fs.s3a.path.style.access=true --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions -e "SELECT snapshot_id, committed_at, operation FROM iceberg.db.transactions.snapshots ORDER BY committed_at DESC LIMIT 5"

# Spark Master UI
# http://localhost:8081

# MinIO HOT UI
# http://localhost:9001
# Login: minioadmin / minioadmin

# MinIO COLD UI
# http://localhost:9101
# Login: minioadmin / minioadmin
```

---

## 🧹 Temizlik

```powershell
# Tüm container'ları durdur ve sil
docker-compose down -v

# Veri klasörlerini temizle
Remove-Item -Recurse -Force data
```

---

## 📊 Mimari Özet

```
┌─────────────────────────────────────────────────────────────┐
│                     APACHE ICEBERG                          │
│                  (Format Version 2)                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    SPARK (3.5.0)                            │
│            Master + Worker + PySpark                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────┬─────────────────────────────────┐
│      MinIO HOT            │       MinIO COLD                │
│  (Primary Storage)        │   (Archive Storage)             │
│  Port: 9000/9001          │   Port: 9100/9101               │
│                           │                                 │
│  • Metadata (always)      │   • Old Data (1+ day)           │
│  • Fresh Data (today)     │   • Manual Tiering Script       │
└───────────────────────────┴─────────────────────────────────┘
```

---

## ✅ Kurulum Tamamlandı!

Tüm komutları sırayla çalıştırdıysan sistem hazır! 🎉

**Özet:**
- ✅ Iceberg tablosu çalışıyor
- ✅ Veri HOT'da
- ✅ Tiering script'i hazır
- ✅ MinIO HOT/COLD izole

**Sonraki Adımlar:**
1. Airflow kurarak otomatik tiering
2. Compaction job ekleme
3. Monitoring & alerting

