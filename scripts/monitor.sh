#!/bin/bash
# Monitoring ve Debugging Utility Script

# Renk kodları
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

show_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  $1${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}\n"
}

# Container durumları
check_containers() {
    show_header "🐳 Container Durumları"
    docker-compose ps
}

# MinIO bucket boyutları
check_storage() {
    show_header "💾 Storage Kullanımı"
    
    echo -e "${YELLOW}HOT TIER:${NC}"
    docker exec minio-mc mc du hot/iceberg-warehouse --recursive
    
    echo -e "\n${YELLOW}COLD TIER:${NC}"
    docker exec minio-mc mc du cold/iceberg-cold-tier --recursive
}

# ILM policy durumu
check_ilm() {
    show_header "⚙️ ILM Policy Durumu"
    docker exec minio-mc mc ilm ls hot/iceberg-warehouse
}

# Remote tier durumu
check_tiers() {
    show_header "🔗 Remote Tier Durumu"
    docker exec minio-mc mc admin tier ls hot
}

# Iceberg tablo istatistikleri
check_iceberg_stats() {
    show_header "📊 Iceberg Tablo İstatistikleri"
    
    docker exec spark-master spark-sql \
        --jars /opt/bitnami/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/bitnami/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/bitnami/spark/jars/custom/hadoop-aws-3.3.4.jar \
        --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog \
        --conf spark.sql.catalog.iceberg.type=hadoop \
        --conf spark.sql.catalog.iceberg.warehouse=s3a://iceberg-warehouse/ \
        --conf spark.sql.catalog.iceberg.io-impl=org.apache.iceberg.aws.s3.S3FileIO \
        --conf spark.hadoop.fs.s3a.endpoint=http://minio-hot:9000 \
        --conf spark.hadoop.fs.s3a.access.key=minioadmin \
        --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
        --conf spark.hadoop.fs.s3a.path.style.access=true \
        --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false \
        --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
        -e "
        USE iceberg;
        
        SELECT 'KAYIT SAYILARI' as metric, '' as value;
        SELECT date, COUNT(*) as record_count FROM db.transactions GROUP BY date ORDER BY date DESC;
        
        SELECT '' as metric, '' as value;
        SELECT 'DOSYA İSTATİSTİKLERİ' as metric, '' as value;
        SELECT 
            partition.date,
            COUNT(*) as file_count,
            ROUND(SUM(file_size_in_bytes) / 1024 / 1024, 2) as total_size_mb,
            ROUND(AVG(file_size_in_bytes) / 1024 / 1024, 2) as avg_file_size_mb
        FROM db.transactions.files
        GROUP BY partition.date
        ORDER BY partition.date DESC;
        " 2>/dev/null || echo -e "${RED}⚠️ Tablo henüz oluşturulmamış${NC}"
}

# Snapshot geçmişi
check_snapshots() {
    show_header "📸 Snapshot Geçmişi"
    
    docker exec spark-master spark-sql \
        --jars /opt/bitnami/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,/opt/bitnami/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,/opt/bitnami/spark/jars/custom/hadoop-aws-3.3.4.jar \
        --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog \
        --conf spark.sql.catalog.iceberg.type=hadoop \
        --conf spark.sql.catalog.iceberg.warehouse=s3a://iceberg-warehouse/ \
        --conf spark.sql.catalog.iceberg.io-impl=org.apache.iceberg.aws.s3.S3FileIO \
        --conf spark.hadoop.fs.s3a.endpoint=http://minio-hot:9000 \
        --conf spark.hadoop.fs.s3a.access.key=minioadmin \
        --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
        --conf spark.hadoop.fs.s3a.path.style.access=true \
        --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false \
        --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
        -e "SELECT * FROM iceberg.db.transactions.snapshots ORDER BY committed_at DESC LIMIT 10" 2>/dev/null || echo -e "${RED}⚠️ Tablo henüz oluşturulmamış${NC}"
}

# System health check
health_check() {
    show_header "🏥 Sistem Sağlık Kontrolü"
    
    echo -e "${YELLOW}MinIO HOT:${NC}"
    docker exec minio-hot curl -sf http://localhost:9000/minio/health/live && echo -e "${GREEN}✅ Sağlıklı${NC}" || echo -e "${RED}❌ Erişilemiyor${NC}"
    
    echo -e "\n${YELLOW}MinIO COLD:${NC}"
    docker exec minio-cold curl -sf http://localhost:9000/minio/health/live && echo -e "${GREEN}✅ Sağlıklı${NC}" || echo -e "${RED}❌ Erişilemiyor${NC}"
    
    echo -e "\n${YELLOW}Spark Master:${NC}"
    docker exec spark-master curl -sf http://localhost:8080 > /dev/null && echo -e "${GREEN}✅ Sağlıklı${NC}" || echo -e "${RED}❌ Erişilemiyor${NC}"
}

# Logları göster
show_logs() {
    show_header "📋 Son Loglar"
    
    echo -e "${YELLOW}Hangi servisin loglarını görmek istersiniz?${NC}"
    echo "1) Spark Master"
    echo "2) Spark Worker"
    echo "3) MinIO HOT"
    echo "4) MinIO COLD"
    echo "5) Tümü"
    read -p "Seçim (1-5): " choice
    
    case $choice in
        1) docker-compose logs --tail=50 spark-master ;;
        2) docker-compose logs --tail=50 spark-worker ;;
        3) docker-compose logs --tail=50 minio-hot ;;
        4) docker-compose logs --tail=50 minio-cold ;;
        5) docker-compose logs --tail=50 ;;
        *) echo -e "${RED}Geçersiz seçim${NC}" ;;
    esac
}

# Test tiering
test_tiering() {
    show_header "🧪 Tiering Testi"
    
    echo -e "${BLUE}Test dosyası oluşturuluyor ve HOT tier'a yükleniyor...${NC}"
    TEST_FILE="/tmp/tiering-test-$(date +%s).txt"
    echo "Test data for tiering - $(date)" > $TEST_FILE
    
    docker exec minio-mc mc cp $TEST_FILE hot/iceberg-warehouse/data/tiering-test.txt
    
    echo -e "\n${GREEN}✅ Test dosyası yüklendi: hot/iceberg-warehouse/data/tiering-test.txt${NC}"
    echo -e "${YELLOW}💡 Bu dosya 1 gün sonra COLD tier'a taşınacak${NC}"
    echo -e "${YELLOW}💡 Test etmek için ILM rule'ı geçici olarak 1 dakikaya ayarlayabilirsiniz${NC}"
    
    rm -f $TEST_FILE
}

# Ana menü
show_menu() {
    clear
    echo -e "${BLUE}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     🔍 Iceberg + MinIO Monitoring & Debug Tool              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    
    echo "1)  🐳 Container Durumları"
    echo "2)  💾 Storage Kullanımı"
    echo "3)  ⚙️  ILM Policy Durumu"
    echo "4)  🔗 Remote Tier Durumu"
    echo "5)  📊 Iceberg İstatistikleri"
    echo "6)  📸 Snapshot Geçmişi"
    echo "7)  🏥 Sistem Sağlık Kontrolü"
    echo "8)  📋 Logları Göster"
    echo "9)  🧪 Tiering Testi"
    echo "10) 🔄 Tümünü Göster"
    echo "0)  ❌ Çıkış"
    echo ""
    read -p "Seçim (0-10): " choice
    
    case $choice in
        1) check_containers ;;
        2) check_storage ;;
        3) check_ilm ;;
        4) check_tiers ;;
        5) check_iceberg_stats ;;
        6) check_snapshots ;;
        7) health_check ;;
        8) show_logs ;;
        9) test_tiering ;;
        10) 
            check_containers
            check_storage
            check_ilm
            check_tiers
            check_iceberg_stats
            health_check
            ;;
        0) 
            echo -e "\n${GREEN}👋 Görüşmek üzere!${NC}\n"
            exit 0
            ;;
        *) 
            echo -e "${RED}Geçersiz seçim${NC}"
            ;;
    esac
    
    echo ""
    read -p "Devam etmek için Enter'a basın..."
    show_menu
}

# Script başlangıcı
if [ "$1" == "--all" ]; then
    # Tümünü göster modu
    check_containers
    check_storage
    check_ilm
    check_tiers
    check_iceberg_stats
    health_check
else
    # İnteraktif menü
    show_menu
fi

