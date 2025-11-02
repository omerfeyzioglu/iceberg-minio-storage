#!/usr/bin/env python3
"""
Iceberg Advanced Query Analysis Script
Kompleks sorgular ve analizler
"""

from pyspark.sql import SparkSession
from datetime import datetime

def create_spark_session():
    """Spark session oluştur"""
    return SparkSession.builder \
        .appName("Iceberg Query Analysis") \
        .getOrCreate()

def print_section(title):
    """Bölüm başlığı yazdır"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def basic_statistics(spark):
    """Temel istatistikler"""
    print_section("TEMEL ISTATISTIKLER")
    
    spark.sql("""
        SELECT 
            date,
            COUNT(*) as transaction_count,
            COUNT(DISTINCT category) as unique_categories,
            COUNT(DISTINCT region) as unique_regions,
            ROUND(SUM(amount), 2) as total_revenue,
            ROUND(AVG(amount), 2) as avg_transaction,
            ROUND(MIN(amount), 2) as min_transaction,
            ROUND(MAX(amount), 2) as max_transaction,
            SUM(quantity) as total_units
        FROM iceberg.db.transactions
        GROUP BY date
        ORDER BY date DESC
    """).show(20, truncate=False)

def category_analysis(spark):
    """Kategori bazlı analiz"""
    print_section("KATEGORI ANALIZI")
    
    spark.sql("""
        SELECT 
            category,
            COUNT(*) as total_transactions,
            ROUND(SUM(amount), 2) as total_revenue,
            ROUND(AVG(amount), 2) as avg_transaction,
            ROUND(100.0 * SUM(amount) / SUM(SUM(amount)) OVER (), 2) as revenue_share_pct,
            SUM(quantity) as total_units,
            ROUND(AVG(quantity), 2) as avg_units_per_txn
        FROM iceberg.db.transactions
        GROUP BY category
        ORDER BY total_revenue DESC
    """).show(truncate=False)

def regional_performance(spark):
    """Bölgesel performans analizi"""
    print_section("BOLGESEL PERFORMANS")
    
    spark.sql("""
        SELECT 
            region,
            date,
            COUNT(*) as transactions,
            ROUND(SUM(amount), 2) as revenue,
            ROUND(AVG(amount), 2) as avg_ticket,
            -- Regional ranking by day
            RANK() OVER (PARTITION BY date ORDER BY SUM(amount) DESC) as daily_rank,
            -- Running total per region
            ROUND(SUM(SUM(amount)) OVER (
                PARTITION BY region 
                ORDER BY date 
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ), 2) as cumulative_revenue
        FROM iceberg.db.transactions
        GROUP BY region, date
        ORDER BY date DESC, revenue DESC
    """).show(30, truncate=False)

def top_performers(spark):
    """En iyi performans gösterenler"""
    print_section("TOP PERFORMANSLAR")
    
    print("\n--- En Çok Satan Kategori-Bölge Kombinasyonları ---")
    spark.sql("""
        SELECT 
            category,
            region,
            COUNT(*) as transactions,
            ROUND(SUM(amount), 2) as total_revenue,
            ROUND(AVG(amount), 2) as avg_transaction
        FROM iceberg.db.transactions
        GROUP BY category, region
        ORDER BY total_revenue DESC
        LIMIT 10
    """).show(truncate=False)
    
    print("\n--- Günlük En Yüksek Gelir ---")
    spark.sql("""
        SELECT 
            date,
            MAX(amount) as highest_transaction,
            MIN(amount) as lowest_transaction,
            ROUND(AVG(amount), 2) as avg_transaction,
            COUNT(*) as total_transactions
        FROM iceberg.db.transactions
        GROUP BY date
        ORDER BY date DESC
    """).show(truncate=False)

def time_series_analysis(spark):
    """Zaman serisi analizi"""
    print_section("ZAMAN SERISI ANALIZI")
    
    spark.sql("""
        WITH daily_stats AS (
            SELECT 
                date,
                COUNT(*) as txn_count,
                ROUND(SUM(amount), 2) as daily_revenue,
                ROUND(AVG(amount), 2) as avg_ticket
            FROM iceberg.db.transactions
            GROUP BY date
        )
        SELECT 
            date,
            txn_count,
            daily_revenue,
            avg_ticket,
            -- Previous day comparison
            LAG(txn_count, 1) OVER (ORDER BY date) as prev_day_txn,
            LAG(daily_revenue, 1) OVER (ORDER BY date) as prev_day_revenue,
            -- Growth calculations
            CASE 
                WHEN LAG(txn_count, 1) OVER (ORDER BY date) IS NOT NULL 
                THEN ROUND(100.0 * (txn_count - LAG(txn_count, 1) OVER (ORDER BY date)) 
                     / LAG(txn_count, 1) OVER (ORDER BY date), 2)
                ELSE NULL 
            END as txn_growth_pct,
            CASE 
                WHEN LAG(daily_revenue, 1) OVER (ORDER BY date) IS NOT NULL 
                THEN ROUND(100.0 * (daily_revenue - LAG(daily_revenue, 1) OVER (ORDER BY date)) 
                     / LAG(daily_revenue, 1) OVER (ORDER BY date), 2)
                ELSE NULL 
            END as revenue_growth_pct
        FROM daily_stats
        ORDER BY date DESC
    """).show(20, truncate=False)

def percentile_distribution(spark):
    """Percentile dağılımı"""
    print_section("FIYAT DAGILIMI (PERCENTILE)")
    
    spark.sql("""
        SELECT 
            category,
            COUNT(*) as transactions,
            ROUND(MIN(amount), 2) as min_price,
            ROUND(PERCENTILE(amount, 0.25), 2) as p25,
            ROUND(PERCENTILE(amount, 0.50), 2) as median,
            ROUND(PERCENTILE(amount, 0.75), 2) as p75,
            ROUND(PERCENTILE(amount, 0.90), 2) as p90,
            ROUND(PERCENTILE(amount, 0.95), 2) as p95,
            ROUND(MAX(amount), 2) as max_price,
            ROUND(AVG(amount), 2) as mean,
            ROUND(STDDEV(amount), 2) as std_dev
        FROM iceberg.db.transactions
        GROUP BY category
        ORDER BY category
    """).show(truncate=False)

def metadata_info(spark):
    """Metadata bilgileri"""
    print_section("METADATA VE DOSYA BILGILERI")
    
    print("\n--- Partition İstatistikleri ---")
    spark.sql("""
        SELECT 
            partition.date,
            file_count,
            ROUND(total_data_file_size_in_bytes / 1024.0 / 1024.0, 2) as size_mb,
            record_count,
            ROUND(total_data_file_size_in_bytes / record_count / 1024.0, 2) as kb_per_record
        FROM iceberg.db.transactions.partitions
        ORDER BY partition.date DESC
    """).show(truncate=False)
    
    print("\n--- Dosya Dağılımı ---")
    spark.sql("""
        SELECT 
            partition.date,
            COUNT(*) as num_files,
            ROUND(SUM(file_size_in_bytes) / 1024.0 / 1024.0, 2) as total_mb,
            ROUND(AVG(file_size_in_bytes) / 1024.0, 2) as avg_file_kb,
            ROUND(MIN(file_size_in_bytes) / 1024.0, 2) as min_file_kb,
            ROUND(MAX(file_size_in_bytes) / 1024.0, 2) as max_file_kb
        FROM iceberg.db.transactions.files
        GROUP BY partition.date
        ORDER BY partition.date DESC
    """).show(truncate=False)
    
    print("\n--- Snapshot Geçmişi (Son 5) ---")
    spark.sql("""
        SELECT 
            committed_at,
            snapshot_id,
            operation,
            summary['added-records'] as added_records,
            summary['total-records'] as total_records,
            summary['total-data-files'] as total_files
        FROM iceberg.db.transactions.snapshots
        ORDER BY committed_at DESC
        LIMIT 5
    """).show(truncate=False)

def pivot_analysis(spark):
    """Pivot analizi - Region vs Category"""
    print_section("PIVOT ANALIZI (Region x Category)")
    
    spark.sql("""
        SELECT * FROM (
            SELECT 
                region,
                category,
                ROUND(SUM(amount), 2) as revenue
            FROM iceberg.db.transactions
            GROUP BY region, category
        )
        PIVOT (
            SUM(revenue)
            FOR category IN ('Electronics', 'Clothing', 'Food', 'Books', 'Sports')
        )
        ORDER BY region
    """).show(truncate=False)

def cohort_analysis(spark):
    """Cohort analizi"""
    print_section("COHORT ANALIZI (Kategori Trendleri)")
    
    spark.sql("""
        WITH daily_category AS (
            SELECT 
                date,
                category,
                COUNT(*) as txn_count,
                ROUND(SUM(amount), 2) as revenue
            FROM iceberg.db.transactions
            GROUP BY date, category
        )
        SELECT 
            date,
            category,
            txn_count,
            revenue,
            -- 3-day moving average
            ROUND(AVG(revenue) OVER (
                PARTITION BY category 
                ORDER BY date 
                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
            ), 2) as ma_3day,
            -- Category rank by day
            RANK() OVER (PARTITION BY date ORDER BY revenue DESC) as daily_rank
        FROM daily_category
        ORDER BY date DESC, revenue DESC
    """).show(30, truncate=False)

def advanced_aggregations(spark):
    """Gelişmiş aggregasyonlar"""
    print_section("GELISMIS AGGREGASYONLAR")
    
    print("\n--- ROLLUP (Hiyerarşik) ---")
    spark.sql("""
        SELECT 
            date,
            region,
            category,
            COUNT(*) as transactions,
            ROUND(SUM(amount), 2) as revenue
        FROM iceberg.db.transactions
        GROUP BY ROLLUP(date, region, category)
        HAVING date IS NOT NULL
        ORDER BY date DESC NULLS LAST, revenue DESC NULLS LAST
        LIMIT 30
    """).show(30, truncate=False)

def custom_metrics(spark):
    """Özel metrikler"""
    print_section("OZEL METRIKLER")
    
    spark.sql("""
        SELECT 
            date,
            -- Transaction segmentation
            COUNT(CASE WHEN amount < 100 THEN 1 END) as small_txn,
            COUNT(CASE WHEN amount BETWEEN 100 AND 500 THEN 1 END) as medium_txn,
            COUNT(CASE WHEN amount > 500 THEN 1 END) as large_txn,
            -- Revenue breakdown
            ROUND(SUM(CASE WHEN amount < 100 THEN amount ELSE 0 END), 2) as small_revenue,
            ROUND(SUM(CASE WHEN amount BETWEEN 100 AND 500 THEN amount ELSE 0 END), 2) as medium_revenue,
            ROUND(SUM(CASE WHEN amount > 500 THEN amount ELSE 0 END), 2) as large_revenue,
            -- Quantity analysis
            ROUND(AVG(CASE WHEN quantity > 50 THEN quantity END), 2) as avg_bulk_order,
            COUNT(CASE WHEN quantity > 50 THEN 1 END) as bulk_order_count
        FROM iceberg.db.transactions
        GROUP BY date
        ORDER BY date DESC
    """).show(truncate=False)

def main():
    """Ana fonksiyon"""
    print("\n" + "=" * 80)
    print("  ICEBERG QUERY ANALYSIS - BASLIYOR")
    print("=" * 80)
    
    spark = create_spark_session()
    
    try:
        # Sırayla tüm analizleri çalıştır
        basic_statistics(spark)
        category_analysis(spark)
        regional_performance(spark)
        top_performers(spark)
        time_series_analysis(spark)
        percentile_distribution(spark)
        pivot_analysis(spark)
        cohort_analysis(spark)
        advanced_aggregations(spark)
        custom_metrics(spark)
        metadata_info(spark)
        
        print("\n" + "=" * 80)
        print("  TUM ANALIZLER TAMAMLANDI")
        print("=" * 80 + "\n")
        
    except Exception as e:
        print(f"\nHATA: {str(e)}")
        raise
    finally:
        spark.stop()

if __name__ == "__main__":
    main()

