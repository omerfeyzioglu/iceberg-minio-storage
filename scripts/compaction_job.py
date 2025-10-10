#!/usr/bin/env python3
"""
Iceberg Compaction Job
Her gece 23:00'da çalışacak
Küçük dosyaları birleştirerek query performansını artırır
"""

from pyspark.sql import SparkSession
from datetime import datetime, timedelta
import time

def create_spark_session():
    """Iceberg + MinIO yapılandırmalı Spark session"""
    return SparkSession.builder \
        .appName("Iceberg Compaction Job") \
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

def get_partition_stats(spark, partition_date):
    """Partition istatistiklerini getir"""
    stats = spark.sql(f"""
        SELECT 
            COUNT(DISTINCT file_path) as file_count,
            SUM(file_size_in_bytes) / 1024 / 1024 as total_size_mb,
            AVG(file_size_in_bytes) / 1024 / 1024 as avg_file_size_mb
        FROM iceberg.db.transactions.files
        WHERE partition.date = DATE'{partition_date}'
    """).collect()[0]
    
    return stats

def compact_partition(spark, partition_date, target_file_size_mb=256):
    """
    Belirli bir partition'ı compact et
    
    Args:
        spark: SparkSession
        partition_date: Compact edilecek partition tarihi
        target_file_size_mb: Hedef dosya boyutu (MB)
    """
    print(f"\n{'='*60}")
    print(f"🔄 COMPACTION: {partition_date}")
    print(f"{'='*60}")
    
    # Compaction öncesi durum
    print("\n📊 Compaction Öncesi:")
    stats_before = get_partition_stats(spark, partition_date)
    print(f"   Dosya sayısı: {stats_before['file_count']}")
    print(f"   Toplam boyut: {stats_before['total_size_mb']:.2f} MB")
    print(f"   Ortalama dosya boyutu: {stats_before['avg_file_size_mb']:.2f} MB")
    
    start_time = time.time()
    
    # Compaction ile rewrite
    print(f"\n⚙️ Compaction başlatılıyor... (Dosyaları birleştiriyoruz)")
    spark.sql(f"""
        CALL iceberg.system.rewrite_data_files(
            table => 'iceberg.db.transactions',
            strategy => 'binpack',
            where => "date = DATE'{partition_date}'",
            options => map(
                'target-file-size-bytes', '{target_file_size_mb * 1024 * 1024}',
                'rewrite-all', 'true'
            )
        )
    """)
    
    duration = time.time() - start_time
    
    # Compaction sonrası durum
    print("\n📊 Compaction Sonrası:")
    stats_after = get_partition_stats(spark, partition_date)
    print(f"   Dosya sayısı: {stats_after['file_count']}")
    print(f"   Toplam boyut: {stats_after['total_size_mb']:.2f} MB")
    print(f"   Ortalama dosya boyutu: {stats_after['avg_file_size_mb']:.2f} MB")
    
    # İyileştirme metrikleri
    size_reduction = ((stats_before['total_size_mb'] - stats_after['total_size_mb']) / 
                      stats_before['total_size_mb'] * 100)
    file_reduction = ((stats_before['file_count'] - stats_after['file_count']) / 
                      stats_before['file_count'] * 100)
    
    print(f"\n✨ Compaction Sonuçları:")
    print(f"   Süre: {duration:.2f} saniye")
    print(f"   Boyut azalması: {size_reduction:.1f}%")
    print(f"   Dosya azalması: {file_reduction:.1f}%")

def expire_snapshots(spark, days_to_keep=7):
    """Eski snapshot'ları temizle"""
    print(f"\n🧹 Eski snapshot'lar temizleniyor... (>{days_to_keep} gün)")
    
    expire_timestamp = datetime.now() - timedelta(days=days_to_keep)
    expire_timestamp_ms = int(expire_timestamp.timestamp() * 1000)
    
    spark.sql(f"""
        CALL iceberg.system.expire_snapshots(
            table => 'iceberg.db.transactions',
            older_than => TIMESTAMP '{expire_timestamp.strftime("%Y-%m-%d %H:%M:%S")}',
            retain_last => 5
        )
    """)
    
    print(f"✅ {days_to_keep} günden eski snapshot'lar temizlendi")

def remove_orphan_files(spark):
    """Orphan dosyaları temizle"""
    print("\n🧹 Orphan dosyalar temizleniyor...")
    
    # 3 günden eski orphan dosyaları sil
    older_than = datetime.now() - timedelta(days=3)
    
    result = spark.sql(f"""
        CALL iceberg.system.remove_orphan_files(
            table => 'iceberg.db.transactions',
            older_than => TIMESTAMP '{older_than.strftime("%Y-%m-%d %H:%M:%S")}'
        )
    """)
    
    print("✅ Orphan dosyalar temizlendi")
    result.show(truncate=False)

def run_nightly_compaction(spark):
    """Gece compaction job'ı"""
    print("\n" + "="*60)
    print("🌙 NIGHTLY COMPACTION JOB")
    print(f"⏰ Çalışma zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Test için: Mevcut partition'ı compact et
    # TODO: Production'da today = datetime.now().date() kullan
    today = datetime(2025, 10, 5).date()
    
    try:
        compact_partition(spark, today, target_file_size_mb=256)
        
        # Maintenance işlemleri
        print("\n" + "="*60)
        print("🛠️ MAINTENANCE İŞLEMLERİ")
        print("="*60)
        
        expire_snapshots(spark, days_to_keep=7)
        remove_orphan_files(spark)
        
        print("\n✅ Nightly compaction job tamamlandı!")
        
    except Exception as e:
        print(f"\n❌ Hata oluştu: {str(e)}")
        raise

def schedule_nightly_job(spark):
    """
    Her gece 23:00'da çalışacak job
    Production'da cron ile çalıştırılmalı: 0 23 * * * python compaction_job.py --schedule
    """
    print("⏰ Scheduler başlatıldı - Her gece 23:00'da compaction çalışacak")
    print("   (Ctrl+C ile durdurun)\n")
    
    while True:
        now = datetime.now()
        
        # 23:00'ı kontrol et
        if now.hour == 23 and now.minute == 0:
            run_nightly_compaction(spark)
            # Bir sonraki güne kadar bekle
            time.sleep(3600)  # 1 saat bekle
        else:
            # 1 dakika bekle
            next_run = now.replace(hour=23, minute=0, second=0, microsecond=0)
            if now.hour >= 23:
                next_run += timedelta(days=1)
            
            print(f"⏳ Bir sonraki çalışma: {next_run.strftime('%Y-%m-%d %H:%M:%S')}", end='\r')
            time.sleep(60)

if __name__ == "__main__":
    import sys
    
    spark = create_spark_session()
    
    try:
        if "--schedule" in sys.argv:
            # Scheduler modu
            schedule_nightly_job(spark)
        else:
            # Tek seferlik çalıştırma
            run_nightly_compaction(spark)
            
    except KeyboardInterrupt:
        print("\n\n⏹️ Job durduruldu")
    finally:
        spark.stop()

